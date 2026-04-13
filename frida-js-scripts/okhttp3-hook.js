/**
 * OkHttp3 + Native 层 Hook 脚本
 *
 * 功能概述：
 *   1. 拦截 OkHttp3 同步/异步请求，打印请求 URL、方法、请求头、请求体
 *   2. 拦截 ResponseBody.string()/bytes()，打印响应体内容（不消耗原始流）
 *   3. 拦截 WebSocket 文本消息发送
 *   4. 拦截 Native JNI 层的加密、解密、签名、验签函数调用
 *
 * 使用方式：
 *   frida -U -f <package_name> -l okhttp3-hook.js
 */

/**
 * 安全获取 Java 类引用，类不存在时返回 null 而不抛异常
 * 应用混淆后类名可能改变，或目标类根本不存在，用此函数避免脚本中断
 * @param {string} className - 完整的 Java 类名，如 "okhttp3.ResponseBody"
 * @returns {Java.Wrapper|null} 类引用，类不存在时返回 null
 */
function tryUse(className) {
    try {
        return Java.use(className);
    } catch (e) {
        console.log("[-] Class not found: " + className);
        return null;
    }
}

/**
 * 将 OkHttp 的 Headers 对象转换为普通 JS 对象
 * OkHttp 的 Headers 是特殊的键值对容器，需要通过迭代器遍历
 * @param {Java.Wrapper} headers - OkHttp Headers 对象
 * @returns {Object} 键值对形式的请求/响应头，如 {"Content-Type": "application/json"}
 */
function formatHeaders(headers) {
    if (!headers) return {};
    var result = {};
    try {
        // OkHttp Headers 的 names() 返回 Set<String>，需用 Java 迭代器遍历
        var names = headers.names();
        var it = names.iterator();
        while (it.hasNext()) {
            var name = it.next();
            result[name] = headers.get(name);
        }
    } catch (e) {}
    return result;
}

/**
 * 安全读取请求体内容
 * 使用 okio.Buffer 写入请求体副本，不会消耗原始请求体流
 * 【重要】绝不能直接调用 body 相关消耗方法，否则会导致应用崩溃
 * @param {Java.Wrapper} request - OkHttp Request 对象
 * @returns {string} 请求体字符串，无请求体时返回空字符串
 */
function readRequestBody(request) {
    try {
        var reqBody = request.body();
        if (reqBody == null) return "";
        // 通过 okio.Buffer 拷贝请求体，writeTo 是复制操作，不会消耗原始流
        var Buffer = Java.use("okio.Buffer");
        var buffer = Buffer.$new();
        reqBody.writeTo(buffer);
        return buffer.readUtf8();
    } catch (e) {
        return "";
    }
}

/**
 * 打印 HTTP 请求信息（URL、方法、请求头、请求体）
 * 请求体超过 2000 字符时截断显示，避免输出过长
 * @param {Java.Wrapper} request - OkHttp Request 对象
 */
function printRequest(request) {
    try {
        var url = request.url().toString();
        var method = request.method();
        var headers = formatHeaders(request.headers());
        var bodyStr = readRequestBody(request);

        console.log("");
        console.log(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>");
        console.log("[Request] " + method + " " + url);
        console.log("--------------------------------------------------------");
        var keys = Object.keys(headers);
        for (var i = 0; i < keys.length; i++) {
            console.log("  " + keys[i] + ": " + headers[keys[i]]);
        }
        if (bodyStr && bodyStr.length > 0) {
            console.log("--------------------------------------------------------");
            var bodyLen = bodyStr.length;
            // 截断至 2000 字符，避免超大请求体撑爆控制台输出
            console.log("  Body (" + bodyLen + "): " +
                bodyStr.substring(0, Math.min(bodyLen, 2000)));
        }
        console.log(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>");
    } catch (e) {
        console.log("[Request print error: " + e.message + "]");
    }
}

/**
 * 打印 HTTP 响应头信息（状态码、响应头）
 * 注意：此处不读取响应体，因为 ResponseBody 是一次性流，不能在 Hook 中消耗
 * 响应体通过单独 Hook ResponseBody.string() / bytes() 来拦截
 * @param {Java.Wrapper} response - OkHttp Response 对象
 */
function printResponseHeaders(response) {
    try {
        // 从 Response 反查关联的 Request，用于拼接完整的请求标识信息
        var request = response.request();
        var url = request.url().toString();
        var method = request.method();
        var code = response.code();
        var msg = response.message();
        var headers = formatHeaders(response.headers());

        console.log("");
        console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
        console.log("[Response] " + code + " " + msg + " (" + method + " " + url + ")");
        console.log("--------------------------------------------------------");
        var keys = Object.keys(headers);
        for (var i = 0; i < keys.length; i++) {
            console.log("  " + keys[i] + ": " + headers[keys[i]]);
        }
        console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
    } catch (e) {
        console.log("[Response headers print error: " + e.message + "]");
    }
}

/**
 * Hook ResponseBody.string() —— 拦截应用读取响应体文本的调用
 * 【关键】ResponseBody 是一次性流，string() 只能调用一次
 * 所以不能在 Response Hook 中调用 body.string() 来预览，只能拦截应用自身的调用
 * 这里拦截返回值（应用已读取的结果），打印后原样返回，不影响应用逻辑
 * 必须遍历所有 overloads（OkHttp4/Kotlin 有多个重载），用 IIFE 捕获变量
 */
function hookResponseBodyString() {
    var ResponseBody = tryUse("okhttp3.ResponseBody");
    if (!ResponseBody) return;

    var overloads = ResponseBody.string.overloads;
    // 必须遍历所有重载：OkHttp4/Kotlin 编译后可能有多个 string() 签名
    // 用 IIFE 包裹，避免循环变量 i 在闭包中被共享（var 是函数作用域）
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            // 替换 string() 的实现：先调用原始方法拿到结果，再拦截打印
            // 应用调用 response.body().string() 时，实际执行的就是这个函数
            overload.implementation = function () {
                // 调用原始 string()，获取返回值（此时流被消耗，但不影响，因为就是这个调用该消耗）
                var result = this.string();
                try {
                    // "" + result：强制将 Java String 转为 JS string
                    // Frida 中 Java 对象和 JS 对象不同，必须转换后才能用 JS 的 .length 属性
                    var str = result ? "" + result : "";
                    // 这里用 str.length（JS 属性），而不是 str.length()（Java 方法）
                    var len = str.length;
                    var preview = str.substring(0, Math.min(len, 2000));
                    console.log("");
                    console.log("<<<<<<<<<<<<<<<< [ResponseBody] <<<<<<<<<<<<<<<<<<<<<<<<");
                    console.log("  Body (" + len + "): " + preview);
                    console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
                } catch (e) {}
                return result;
            };
        })(overloads[i]);
    }
}

/**
 * Hook ResponseBody.bytes() —— 拦截应用读取响应体字节数组的调用
 * 与 string() 同理，bytes() 也是一次性消耗操作，只能拦截不能主动调用
 * 这里仅记录字节数组长度，不做完整内容输出（二进制数据不适合打印）
 */
function hookResponseBodyBytes() {
    var ResponseBody = tryUse("okhttp3.ResponseBody");
    if (!ResponseBody) return;

    var overloads = ResponseBody.bytes.overloads;
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            // 与 hookResponseBodyString 同理：替换实现，拦截返回值，原样返回
            overload.implementation = function () {
                // 调用原始 bytes()，触发实际的流读取
                var result = this.bytes();
                try {
                    // result 是 Java byte[]，.length 在 Frida 中可直接获取数组长度
                    var len = result ? result.length : 0;
                    console.log("[ResponseBody.bytes] length=" + len);
                } catch (e) {}
                return result;
            };
        })(overloads[i]);
    }
}

// 用于生成唯一的动态注册类名，避免 Java.registerClass 名称冲突
var cbCounter = 0;

// 请求去重计数器，用于区分同一请求的多次调用（避免 getResponseWithInterceptorChain 和 enqueue callback 双重打印）
var dedupCounter = 0;

/**
 * 请求去重集合：只在同一次请求链内去重
 * 避免 getResponseWithInterceptorChain 和 enqueue callback 的 onResponse 对同一个请求重复打印
 * key 由请求的唯一 ID（在 enqueue 中生成）标识，而非 URL+状态码（同一 URL 可能被多次请求）
 */
var printedRequests = {};

/**
 * 标记一个请求为已打印，返回 true 表示首次标记（应打印），false 表示已打印过（跳过）
 */
function markPrinted(key) {
    if (printedRequests[key]) return false;
    printedRequests[key] = true;
    // 10 秒后自动清除，允许后续相同请求正常打印
    setTimeout(function () {
        delete printedRequests[key];
    }, 10000);
    return true;
}

/**
 * 从 Java 类的方法列表中搜索匹配指定关键词的方法名
 * OkHttp4 Kotlin 编译后方法名可能带各种后缀（如 $okhttp, $api 等），无法穷举
 * 通过关键词模糊匹配自动发现正确的方法名，适应任意版本的 OkHttp
 *
 * @param {Java.Wrapper} cls - Frida Java.use() 返回的类引用
 * @param {string} keyword - 方法名关键词，如 "getResponseWithInterceptorChain"
 * @returns {string|null} 匹配到的方法名，未找到返回 null
 */
function findMethodByName(cls, keyword) {
    try {
        var methods = cls.class.getDeclaredMethods();
        for (var i = 0; i < methods.length; i++) {
            var name = methods[i].getName();
            if (name.indexOf(keyword) !== -1) {
                return name;
            }
        }
    } catch (e) {}
    return null;
}

/**
 * Hook OkHttp RealCall —— 拦截所有 HTTP 请求和响应
 *
 * 智能搜索策略：
 *   1. 先尝试多个已知 RealCall 类路径（不同 OkHttp 版本位置不同）
 *   2. 在找到的类中自动搜索包含 "getResponseWithInterceptorChain" 的方法
 *      无论方法名带什么后缀（$okhttp, $api, ProGuard 混淆等）都能匹配
 *   3. 如果搜索不到，再降级到 execute() 作为 fallback
 *   4. 同时 Hook enqueue(callback) 的 onResponse 作为双保险 + onFailure 捕获失败
 *   5. 使用 markPrinted() 去重，避免两个策略都触发时双重打印
 */
function hookRealCall() {
    // OkHttp 不同版本的 RealCall 类路径不同，依次尝试
    var classPaths = [
        "okhttp3.internal.connection.RealCall",
        "okhttp3.RealCall"
    ];
    var cls = null;
    for (var ci = 0; ci < classPaths.length; ci++) {
        cls = tryUse(classPaths[ci]);
        if (cls) {
            console.log("[+] Found RealCall: " + classPaths[ci]);
            break;
        }
    }
    if (!cls) {
        console.log("[-] RealCall class not found in any known path");
        return;
    }

    // --- 策略1：自动搜索并 Hook getResponseWithInterceptorChain ---
    // 不硬编码方法名，而是通过关键词在类的所有方法中模糊搜索
    var getRespMethod = findMethodByName(cls, "getResponseWithInterceptorChain");

    if (getRespMethod) {
        var getRespOv = cls[getRespMethod].overloads;
        for (var i = 0; i < getRespOv.length; i++) {
            (function (overload, methodName) {
                overload.implementation = function () {
                    var resp = this[methodName]();
                    try {
                        // 用 Response 对象的 hashCode 唯一标识本次请求
                        // 同一次请求的 Response 对象在 getResponseWithInterceptorChain 和 onResponse 中是同一个
                        var key = "" + resp.hashCode();
                        if (markPrinted(key)) {
                            printRequest(resp.request());
                            printResponseHeaders(resp);
                        }
                    } catch (e) {
                        console.log("[hook " + methodName + " print error: " + e.message + "]");
                    }
                    return resp;
                };
            })(getRespOv[i], getRespMethod);
        }
        console.log("[+] Hooked " + getRespMethod);
    } else {
        // 搜索不到，降级到 Hook execute()
        console.log("[-] getResponseWithInterceptorChain not found, falling back to execute()");
        if (cls.execute) {
            var execOv = cls.execute.overloads;
            for (var i = 0; i < execOv.length; i++) {
                (function (overload) {
                    overload.implementation = function () {
                        var resp = this.execute();
                        try {
                            printRequest(resp.request());
                            printResponseHeaders(resp);
                        } catch (e) {
                            console.log("[hook execute print error: " + e.message + "]");
                        }
                        return resp;
                    };
                })(execOv[i]);
            }
            console.log("[+] Hooked execute");
        }
    }

    // --- 策略2：Hook enqueue(callback) ---
    // 双重作用：(a) 作为策略1的备份打印请求/响应信息 (b) 捕获 onFailure 失败场景
    if (cls.enqueue) {
        var enqOv = cls.enqueue.overloads;
        for (var i = 0; i < enqOv.length; i++) {
            (function (overload) {
                overload.implementation = function (callback) {
                    var origCb = Java.retain(callback);
                    var idx = ++cbCounter;
                    var Callback = Java.use("okhttp3.Callback");

                    try {
                        var Wrapped = Java.registerClass({
                            name: "com.hook.OkCb" + idx,
                            implements: [Callback],
                            methods: {
                                // 请求成功回调：作为备份打印请求/响应信息（策略1可能未触发）
                                onResponse: function (call, response) {
                                    try {
                                        // 用 Response 的 hashCode 标识，与 getResponseWithInterceptorChain Hook 共享同一个 key
                                        // 如果策略1已打印过，这里自动跳过；如果策略1未触发，这里补打
                                        var key = "" + response.hashCode();
                                        if (markPrinted(key)) {
                                            printRequest(response.request());
                                            printResponseHeaders(response);
                                        }
                                    } catch (e) {}
                                    origCb.onResponse(call, response);
                                },
                                // 请求失败回调：打印失败信息
                                onFailure: function (call, e) {
                                    try {
                                        var req = call.request();
                                        console.log("");
                                        console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
                                        console.log("[Failure] " + req.method() + " " + req.url().toString());
                                        console.log("  Error: " + e.getMessage());
                                        console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
                                    } catch (ex) {}
                                    origCb.onFailure(call, e);
                                }
                            }
                        });
                        return this.enqueue(Wrapped.$new());
                    } catch (regErr) {
                        // Java.registerClass 失败（版本兼容性等），降级到直接调用
                        console.log("[-] registerClass failed, fallback to direct enqueue: " + regErr.message);
                        return this.enqueue(callback);
                    }
                };
            })(enqOv[i]);
        }
        console.log("[+] Hooked enqueue");
    }
}

/**
 * Hook WebSocket 发送消息
 * 拦截 RealWebSocket.send()，打印通过 WebSocket 发送的文本内容
 * 仅 Hook 文本消息发送（send(String)），不包括二进制帧
 */
function hookWebSocket() {
    var cls = tryUse("okhttp3.internal.ws.RealWebSocket");
    if (!cls) return;

    var ov = cls.send.overloads;
    for (var i = 0; i < ov.length; i++) {
        (function (overload) {
            overload.implementation = function (text) {
                // 打印发送的文本内容后，调用原始 send() 确保消息正常发出
                console.log("[WebSocket TX] " + text);
                return this.send(text);
            };
        })(ov[i]);
    }
}

/**
 * Hook Native 层 JNI 加密/解密/签名函数
 * 通过 Frida 的 Interceptor 拦截 libnative-lib.so 中的导出函数
 *
 * 【重要】Native Hook 必须在 Java.perform() 外部执行，否则会报 TypeError
 * SO 库可能延迟加载，采用轮询模式：每秒检查一次模块是否已加载
 *
 * 拦截的函数类型（通过函数名关键词匹配）：
 *   - encrypt:   加密函数，读取输入明文
 *   - decrypt:   解密函数，读取输入密文
 *   - sign:      签名函数，读取待签名数据
 *   - verifySignature: 签名验证，读取数据和签名，打印验证结果(true/false)
 */
function hookNativeCrypto() {
    console.log("[*] Hooking NativeCrypto JNI methods...");

    var libName = "libnative-lib.so";

    // 尝试立即 Hook，如果 SO 库尚未加载则启动轮询等待
    function doHook() {
        var mod = Process.findModuleByName(libName);
        if (!mod) return false;

        console.log("[+] " + libName + " base: " + mod.baseAddress);
        // 枚举 SO 库所有导出符号，筛选 JNI 相关函数
        var exports = mod.enumerateExports();
        console.log("[+] Found " + exports.length + " exports");

        for (var i = 0; i < exports.length; i++) {
            var exp = exports[i];
            // 仅关注函数类型的导出符号，过滤掉变量等其他类型
            if (exp.type !== "function") continue;
            // 按命名规则筛选：包含 "NativeCrypto" 或 "native_" 的才是目标 JNI 函数
            if (exp.name.indexOf("NativeCrypto") === -1 && exp.name.indexOf("native_") === -1) continue;

            console.log("[+] Export: " + exp.name + " @ " + exp.address);

            // 使用 IIFE 捕获循环变量，避免闭包变量共享问题
            (function (exportName, exportAddr) {
                // onEnter: 函数调用前执行，读取输入参数
                // onLeave: 函数返回后执行，读取返回值
                Interceptor.attach(exportAddr, {
                    onEnter: function (args) {
                        try {
                            // 通过 JNI Env 读取 Java String 参数
                            // JNI 函数签名：Java_包名_方法名(JNIEnv* env, jobject thiz, ...)
                            // 所以 args[0]=JNIEnv*, args[1]=this(对象实例), 从 args[1] 起是实际参数
                            // 但此处 JNI 是静态方法，args[1] 就是第一个 Java 参数
                            var env = Java.vm.getEnv();
                            if (exportName.indexOf("encrypt") !== -1) {
                                this.fnType = "encrypt";
                                // env.getStringUtfChars() 返回 Native 指针，需再调用 .readUtf8String() 转为 JS 字符串
                                this.input = env.getStringUtfChars(args[1], null).readUtf8String();
                                console.log("[Native] encrypt(\"" + this.input + "\")");
                            } else if (exportName.indexOf("decrypt") !== -1) {
                                this.fnType = "decrypt";
                                this.input = env.getStringUtfChars(args[1], null).readUtf8String();
                                console.log("[Native] decrypt(\"" + this.input + "\")");
                            } else if (exportName.indexOf("verifySignature") !== -1) {
                                this.fnType = "verifySignature";
                                // verifySignature 有两个参数：待验证数据(args[1]) 和 签名(args[2])
                                this.data = env.getStringUtfChars(args[1], null).readUtf8String();
                                this.sig = env.getStringUtfChars(args[2], null).readUtf8String();
                                console.log("[Native] verifySignature(data=\"" + this.data + "\", sig=\"" + this.sig + "\")");
                            } else if (exportName.indexOf("sign") !== -1 && exportName.indexOf("verify") === -1) {
                                // 注意：sign 匹配时要排除 "verifySignature"（它也包含 "sign"）
                                this.fnType = "sign";
                                this.data = env.getStringUtfChars(args[1], null).readUtf8String();
                                console.log("[Native] sign(\"" + this.data + "\")");
                            }
                        } catch (e) {}
                    },
                    onLeave: function (retval) {
                        try {
                            // onLeave 在函数返回时触发，retval 是 Native 返回值
                            // this.fnType 在 onEnter 中设置，通过 this 传递状态到 onLeave
                            if (this.fnType === "verifySignature") {
                                // JNI boolean 在 Native 层是 jint，toInt32() 后非零为 true
                                console.log("[Native] verifySignature -> " + (retval.toInt32() ? "true" : "false"));
                            } else if (this.fnType) {
                                console.log("[Native] " + this.fnType + " -> retval=" + retval);
                            }
                        } catch (e) {}
                    }
                });
            })(exp.name, exp.address);
        }
        return true;
    }

    // SO 库可能延迟加载，轮询等待直到模块可用
    try {
        if (!doHook()) {
            console.log("[-] " + libName + " not loaded, waiting...");
            // 每秒轮询一次，直到 SO 库加载成功
            var timer = setInterval(function () {
                try { if (doHook()) clearInterval(timer); } catch (e) { clearInterval(timer); }
            }, 1000);
        }
    } catch (e) {
        console.log("[-] Native hook error: " + e.message);
    }
}

/**
 * Java 层 Hook 入口
 * 安装所有 OkHttp3 相关 Hook：
 *   - RealCall (同步/异步请求)
 *   - ResponseBody.string() / bytes() (响应体读取)
 *   - WebSocket.send() (WebSocket 消息发送)
 */
function hookJava() {
    console.log("============================================================");
    console.log("[*] OkHttp3 + Native Hook Script Starting...");
    console.log("============================================================");

    hookRealCall();
    hookResponseBodyString();
    hookResponseBodyBytes();
    hookWebSocket();

    console.log("[+] All hooks installed");
}

// 脚本入口：延迟 3 秒后启动，等待目标应用完成初始化
// Java.perform() 内执行所有 Java 层 Hook
// hookNativeCrypto() 在 Java.perform() 外部执行（Native API 是 Frida 全局 API，不属于 Java Bridge）
setTimeout(function () {
    Java.perform(function () {
        hookJava();
    });
    hookNativeCrypto();
}, 3000);
