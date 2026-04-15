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
 * @param {Java.Wrapper} response - OkHttp Response 对象
 * @param {number} code - HTTP 状态码（由调用方传入，避免内部调用 response.code() 触发递归）
 */
function printResponseHeaders(response, code) {
    try {
        var request = response.request();
        var url = request.url().toString();
        var method = request.method();
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
 * Hook ResponseBody.string() —— 核心拦截点
 *
 * 这是整个脚本中最稳定的 Hook 点，100% 触发。
 * 应用调用 response.body().string() 时触发，此时：
 *   - Response 对象完全可用（通过 Java.choose 按线程查找）
 *   - response.request() 包含经过所有拦截器处理后的完整请求头
 *   - response.code() / response.headers() 包含完整响应信息
 *
 * 所以在此 Hook 中一次性打印：请求头 + 响应头 + 响应体
 *
 * 【安全】只拦截 string() 返回值，不额外消耗流
 */
function hookResponseBodyString() {
    var ResponseBody = tryUse("okhttp3.ResponseBody");
    if (!ResponseBody) return;

    var overloads = ResponseBody.string.overloads;
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            overload.implementation = function () {
                var result = this.string();
                try {
                    var str = result ? "" + result : "";
                    var len = str.length;

                    // 通过 Java.choose 在堆上查找持有当前 ResponseBody 的 Response 对象
                    // 匹配到后，一次打印完整的请求头+响应头
                    // 使用全局的 markResponsePrinted 与 hookResponseClose 共享去重状态
                    var Response = Java.use("okhttp3.Response");
                    var currentBody = this;
                    var foundResponse = null;

                    Java.choose("okhttp3.Response", {
                        onMatch: function (instance) {
                            try {
                                var body = instance.body();
                                if (body !== null && body.equals(currentBody)) {
                                    foundResponse = instance;
                                }
                            } catch (e) {}
                        },
                        onComplete: function () {}
                    });

                    if (foundResponse) {
                        var key = "" + foundResponse.hashCode();
                        if (markResponsePrinted(key)) {
                            printRequest(foundResponse.request());
                            printResponseHeaders(foundResponse, foundResponse.code());
                        }
                    }

                    console.log("");
                    console.log("<<<<<<<<<<<<<<<< [ResponseBody] <<<<<<<<<<<<<<<<<<<<<<<<");
                    console.log("  Body (" + len + "): " + str.substring(0, Math.min(len, 2000)));
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

/**
 * Hook OkHttp 请求和响应
 *
 * 经过反复测试，以下 OkHttp 方法的 Frida Hook 是稳定的：
 *   ✅ ResponseBody.string() — 一直稳定触发
 *   ✅ ResponseBody.bytes() — 一直稳定触发
 *   ✅ RealCall.enqueue() — 一直稳定触发
 *   ✅ RealCall.execute() — 一直稳定触发
 *
 * 以下方法 Hook 安装成功但 implementation 不触发（ART 优化/Kotlin 编译问题）：
 *   ❌ getResponseWithInterceptorChain$okhttp
 *   ❌ RealInterceptorChain.proceed()
 *   ❌ Response.code()
 *
 * 最终方案：利用稳定触发的 Hook 点组合完成全量信息采集
 *   - enqueue()/execute() → 打印请求 URL 摘要（此时请求头可能不完整）
 *   - ResponseBody.string()/bytes() → 打印完整的请求头+响应头+响应体
 *     因为此时 Response 对象完全可用，通过 Frida JNI 反射读取所有信息
 */
// 已打印过完整信息的 Response 去重集合，避免 hookResponseBodyString 和 hookResponseClose 重复打印
// key = Response.hashCode(), value = true
var printedResponses = {};

/**
 * 标记 Response 已打印，返回 true 表示首次（应打印）
 * 3 秒后自动清理，防止内存泄漏
 */
function markResponsePrinted(key) {
    if (printedResponses[key]) return false;
    printedResponses[key] = true;
    setTimeout(function () { delete printedResponses[key]; }, 3000);
    return true;
}

/**
 * Hook OkHttp 请求和响应
 *
 * 三个 Hook 点组合，覆盖成功和失败场景：
 *
 *   1. enqueue() / execute() — 打印完整请求信息（所有场景，包括失败）
 *      enqueue 时 this.request() 可能缺少拦截器添加的自定义头，但基本信息（URL、method、用户自定义头）都有
 *
 *   2. ResponseBody.string() — 打印完整响应头+响应体（仅成功场景）
 *      应用调用 response.body().string() 时触发，通过 Java.choose 找到 Response 打印完整信息
 *
 *   3. Response.close() — 打印即将被关闭的响应信息（覆盖失败/重试场景）
 *      当 RetryInterceptor 关闭非成功响应（如 405）时触发，此时 Response 信息完整可用
 *      使用 markResponsePrinted 与 hookResponseBodyString 去重，避免成功时双重打印
 */
function hookRealCall() {
    var callPaths = [
        "okhttp3.internal.connection.RealCall",
        "okhttp3.RealCall"
    ];
    var cls = null;
    for (var ci = 0; ci < callPaths.length; ci++) {
        cls = tryUse(callPaths[ci]);
        if (cls) {
            console.log("[+] Found RealCall: " + callPaths[ci]);
            break;
        }
    }
    if (!cls) {
        console.log("[-] RealCall class not found");
        return;
    }

    // Hook enqueue：打印完整请求信息
    if (cls.enqueue) {
        var enqOv = cls.enqueue.overloads;
        for (var i = 0; i < enqOv.length; i++) {
            (function (overload) {
                overload.implementation = function (callback) {
                    try {
                        // this.request() 包含用户在 RequestBuilder 中设置的头
                        // 但不包含 AppInterceptor 添加的 X-App-Version 等（那些在拦截器链中才加上）
                        printRequest(this.request());
                    } catch (e) {}
                    return this.enqueue(callback);
                };
            })(enqOv[i]);
        }
        console.log("[+] Hooked enqueue");
    }

    // Hook execute：直接打印完整信息
    if (cls.execute) {
        var execOv = cls.execute.overloads;
        for (var i = 0; i < execOv.length; i++) {
            (function (overload) {
                overload.implementation = function () {
                    var resp = this.execute();
                    try {
                        printRequest(resp.request());
                        printResponseHeaders(resp, resp.code());
                    } catch (e) {}
                    return resp;
                };
            })(execOv[i]);
        }
        console.log("[+] Hooked execute");
    }
}

/**
 * Hook Response.close() —— 捕获失败/重试场景下即将被关闭的响应
 *
 * 场景：RetryInterceptor 收到非成功响应（如 405）后关闭 Response 重试
 * 此时 Response 信息完整可用，但如果不在此捕获就永远丢失了
 * 成功场景下 Response 也会被关闭，但此时信息已由 hookResponseBodyString 打印过
 * 通过 markResponsePrinted 去重，确保不重复打印
 */
function hookResponseClose() {
    var Response = tryUse("okhttp3.Response");
    if (!Response || !Response.close) return;

    var closeOv = Response.close.overloads;
    for (var i = 0; i < closeOv.length; i++) {
        (function (overload) {
            overload.implementation = function () {
                try {
                    var key = "" + this.hashCode();
                    if (markResponsePrinted(key)) {
                        printResponseHeaders(this, this.code());
                    }
                } catch (e) {}
                return this.close();
            };
        })(closeOv[i]);
    }
    console.log("[+] Hooked Response.close");
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
    hookResponseClose();
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
