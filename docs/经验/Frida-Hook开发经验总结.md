# Frida Hook 开发经验总结

> 基于 OkHttp3 Hook 开发过程中的踩坑经验整理，目标是下次编写 Hook 代码时不再踩同样的坑。

---

## 一、核心原则

### 原则 1：不破坏被 Hook 对象的状态

**永远不要在 hook 中消耗一次性资源。**

```
ResponseBody 是一次性流（one-shot stream）
  ├── body.string()   → 消耗 buffer，之后不可再读
  ├── body.bytes()    → 同上
  ├── body.byteStream() → 同上
  └── response.peekBody() → 看似安全，实际在某些 OkHttp 版本会触发 native crash (SIGSEGV)
```

在 `RealCall.execute` / `RealCall.enqueue` 的 hook 中主动调用上述任何方法，都会消耗 body。当 app 自己再读时就会得到：
- `IllegalStateException: closed`
- SIGSEGV（native 层段错误，直接杀进程）

#### 正确策略：被动拦截

不要主动去读，而是 **hook 消费端**，等 app 自己调用时拦截返回值：

```
错误做法：
  hook RealCall.execute → 主动调用 body.string() 打印 → 崩溃

正确做法：
  hook RealCall.execute → 只打印 request/response headers（不碰 body）
  hook ResponseBody.string() → 等app自己调用时拦截返回值打印
  hook ResponseBody.bytes() → 同上
```

#### RequestBody 为什么可以主动读？

```
RequestBody 可以用 okio.Buffer 读取：
  var buffer = Buffer.$new();
  reqBody.writeTo(buffer);   // 写入副本，不消耗原始 body
  return buffer.readUtf8();  // 安全读取
```

因为 `writeTo()` 是将 body 内容**复制**到 buffer，原始 body 不受影响。这与 ResponseBody 的读取方式有本质区别。

#### ⚠️ RequestBody 的 writeTo 也不能在循环中反复调用

虽然 `writeTo()` 是复制操作不消耗原始 body，但在**拦截器链等多层嵌套场景**中，每一层都会触发 hook，如果每层都调用 `readRequestBody`（内部调 `writeTo`），对 POST 请求可能导致异常。

**规则：body 只在最终需要打印时读取一次，不要在中间层提前读取。**

#### 判断标准

```
能否主动调用某方法？
  ├── 该方法是否会修改对象状态？ → 不能
  ├── 该方法是否消耗底层资源（流、buffer、连接）？ → 不能
  ├── 该方法是否有 side effect？ → 谨慎
  └── 该方法是否是纯读取/复制？ → 可以
```

### 原则 2：数据立即提取为纯 JS 值，不存 Java Wrapper

这是第二大坑。Frida 的 Java wrapper 是 JNI 引用，随时可能被 GC 回收。

```javascript
// ❌ 错误：存了 Java wrapper，后续访问时可能已被 GC
var savedRequest = request;  // Java wrapper
setTimeout(function () {
    savedRequest.url();  // "Wrapper is disposed" 异常
}, 100);

// ❌ 错误：从 Java 对象提取的值也可能是 Java wrapper
var headers = {};
headers["key"] = request.headers().get("key");  // 值是 Java String wrapper
// 后续访问 headers["key"] 时可能已 disposed

// ✅ 正确：立即用 "" + 强制转为 JS 原生值
var url = "" + request.url().toString();        // JS string
var method = "" + request.method();              // JS string
var headers = {};
var names = request.headers().names();
var it = names.iterator();
while (it.hasNext()) {
    var name = "" + it.next();                   // JS string
    headers[name] = "" + request.headers().get(name);  // JS string
}
```

**规则：任何从 Java 对象取的值，在存入变量/对象/数组时，立刻 `"" +` 转为 JS 原生值。**

### 原则 3：Hook 中的打印必须在原始调用之前

```javascript
// ❌ 错误：打印在 this.proceed() 之后
// 即使数据是在之前提取的，如果 this.proceed() 抛异常，打印可能拿不到数据
overload.implementation = function (request) {
    var info = extract(request);
    var resp = this.proceed(request);  // 如果抛异常？
    printInfo(info);                    // 可能执行不到
    return resp;
};

// ✅ 正确：打印在 this.proceed() 之前
// 即使后续抛异常，请求信息也已经打印了
overload.implementation = function (request) {
    var info = extract(request);
    printInfo(info);                    // 先打印，确保不丢
    var resp = this.proceed(request);   // 后调用原始方法
    return resp;
};
```

**规则：关键信息的打印放在原始方法调用之前，这样即使原始方法抛异常也不丢失。**

### 原则 4：统一日志函数，禁止 console.log("")

```javascript
// ✅ 统一日志函数
function tsLog(msg) {
    var d = new Date();
    var ts = d.getHours() + ":" +
        ("0" + d.getMinutes()).slice(-2) + ":" +
        ("0" + d.getSeconds()).slice(-2) + "." +
        ("00" + d.getMilliseconds()).slice(-3);
    console.log("[" + ts + "] " + msg);
}

// ❌ 禁止 console.log("") — Frida 中空字符串 log 可能静默失败，吞掉后续输出
// ❌ 禁止直接 console.log(msg) — 无法统一加时间戳、过滤等
```

**规则：所有日志输出用统一的 tsLog 函数，禁止直接 console.log，禁止 console.log("")。**

---

## 二、Hook 架构模式

### 2.1 主动拦截 vs 被动拦截

| 场景 | 模式 | 说明 |
|------|------|------|
| Request headers | 主动拦截 | 在 hook 中直接读取，headers 是纯数据，无 side effect |
| Request body | 主动拦截 | 用 okio.Buffer 复制读取，**但只在最终打印时读一次** |
| Response headers | 主动拦截 | 同 request headers |
| Response body | **被动拦截** | hook ResponseBody.string()/bytes()，不主动消耗 |
| Native 函数参数/返回值 | 被动拦截 | Interceptor.attach 的 onEnter/onLeave |

### 2.2 标准 Hook 模板（修订版）

```javascript
function tsLog(msg) {
    var d = new Date();
    var ts = d.getHours() + ":" +
        ("0" + d.getMinutes()).slice(-2) + ":" +
        ("0" + d.getSeconds()).slice(-2) + "." +
        ("00" + d.getMilliseconds()).slice(-3);
    console.log("[" + ts + "] " + msg);
}

function tryUse(className) {
    try { return Java.use(className); } catch (e) { return null; }
}

// 数据提取函数：立即转纯 JS，不存 Java wrapper，不读 body
function extractInfo(javaObj) {
    return {
        field1: "" + javaObj.field1(),
        field2: "" + javaObj.field2(),
        // body 等消耗性操作不在 extract 中读取
    };
}

// 打印函数：body 只在此处按需读取一次
function printInfo(info, javaObj) {
    tsLog("field1: " + info.field1);
    try {
        var bodyStr = readBody(javaObj);  // 只在打印时读一次
        if (bodyStr) tsLog("body: " + bodyStr);
    } catch (e) {}
}

function hookSomething() {
    var cls = tryUse("com.example.TargetClass");
    if (!cls) return;

    var overloads = cls.targetMethod.overloads;
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            overload.implementation = function (arg) {
                // 1. 立即提取数据为纯 JS 值（不包含 body）
                var info = extractInfo(arg);

                // 2. 在原始调用前打印（即使原始调用抛异常也不丢失）
                printInfo(info, arg);

                // 3. 调用原始方法
                var result = this.targetMethod(arg);

                // 4. 原始调用后打印结果（在 try-catch 中）
                try {
                    printResult(result);
                } catch (e) {
                    tsLog("[hook error] " + e.message);
                }

                return result;
            };
        })(overloads[i]);
    }
}
```

关键点：
1. **数据提取在原始调用前完成**，转为纯 JS 值
2. **打印在原始调用前**，确保即使异常也不丢失
3. **body 只在打印函数中按需读取一次**
4. **所有 Java 值用 `"" +` 转为 JS 原生值**
5. **统一用 tsLog 输出**

### 2.3 链式调用（拦截器链）Hook 模式

框架的拦截器链是嵌套结构，`proceed` 会被每层调用一次，每层的 request 可能被当前拦截器修改：

```
proceed(req0)                          ← 最外层，request 不完整
  → InterceptorA.intercept(chain1)
    → chain1.proceed(req1)             ← InterceptorA 可能修改了 request
      → InterceptorB.intercept(chain2)
        → chain2.proceed(req2)         ← InterceptorB 可能又修改了 request
          → CallServerInterceptor      ← 真正发送网络请求
```

**问题**：最外层的 request 头不完整（拦截器还没修改），最内层才完整。

**解决方案**：用头数量增长判断完整性，只在头增长时打印：

```javascript
var chainThreadMap = {};
var lastChainRequest = {};
var lastChainHeaderCount = {};

function hookInterceptorChain() {
    var cls = tryUse("okhttp3.internal.http.RealInterceptorChain");
    if (!cls || !cls.proceed) return;

    for (var i = 0; i < cls.proceed.overloads.length; i++) {
        (function (overload) {
            overload.implementation = function (request) {
                var tid = Process.getCurrentThreadId();
                var isOuterCall = !chainThreadMap[tid];

                if (isOuterCall) {
                    chainThreadMap[tid] = true;
                    lastChainHeaderCount[tid] = 0;
                }

                // 提取当前层 request 信息（纯 JS 值，不含 body）
                var info = extractRequestHeaders(request);
                var headerCount = Object.keys(info.headers).length;

                // 只在头数量增长时打印（说明拦截器添加了新头）
                if (headerCount > lastChainHeaderCount[tid]) {
                    lastChainRequest[tid] = info;
                    lastChainHeaderCount[tid] = headerCount;
                    printRequestInfo(info);  // 打印在 proceed 之前
                }

                var resp = this.proceed(request);

                if (isOuterCall) {
                    delete chainThreadMap[tid];
                    delete lastChainHeaderCount[tid];
                    delete lastChainRequest[tid];
                    try {
                        printResponseHeaders(resp, resp.code());
                    } catch (e) {}
                }

                return resp;
            };
        })(cls.proceed.overloads[i]);
    }
}
```

---

## 三、Frida Java Bridge 陷阱

### 3.1 Java 方法包装器不是普通 JS Function

```javascript
// ❌ 这些全部不支持
this.someMethod.call(null, arg);
this.someMethod.apply(this, args);
this.someMethod.bind(this);

// ✅ 正确调用方式
this.someMethod(arg1, arg2);
var result = this.someMethod(arguments[0], arguments[1]);
```

Frida 包装的 Java 方法是特殊对象，不是 `Function` 的实例。

### 3.2 字符串类型混淆

Frida 中 Java String 和 JS String 的边界模糊，容易出错：

```javascript
// ❌ 不确定时不要假设类型
str.length()   // Java String 方法？还是 JS 会报错？
str.length     // JS 属性？还是 Java field？

// ✅ 安全做法：强制转为 JS string
var str = "" + someJavaObj.toString();
var len = str.length;  // JS 属性，100% 安全
var preview = str.substring(0, Math.min(len, 2000));  // JS 方法，100% 安全
```

**规则：需要做 JS 字符串操作时，先用 `"" + value` 强制转为 JS string。此规则适用于所有从 Java 对象获取的值（包括 headers 的 key/value、iterator 的返回值等）。**

### 3.3 for 循环中的闭包变量捕获

```javascript
// ❌ 错误：所有回调共享同一个 exp 变量
for (var i = 0; i < exports.length; i++) {
    var exp = exports[i];
    Interceptor.attach(exp.address, {
        onEnter: function (args) {
            console.log(exp.name);  // 永远是最后一个 export 的名字！
        }
    });
}

// ✅ 正确：用 IIFE 捕获当前值
for (var i = 0; i < exports.length; i++) {
    var exp = exports[i];
    (function (exportName, exportAddr) {
        Interceptor.attach(exportAddr, {
            onEnter: function (args) {
                console.log(exportName);  // 每个回调有自己的值
            }
        });
    })(exp.name, exp.address);
}
```

这在以下场景都会出现，必须用 IIFE：
- 遍历 `method.overloads` 数组
- 遍历 `module.enumerateExports()` 结果
- 任何循环中创建 `Interceptor.attach` 或 `Java.use` 回调

### 3.4 Java Wrapper 的 GC 问题（"Wrapper is disposed"）

这是最常见的运行时错误之一。Frida 的 Java wrapper 是 JNI 引用，GC 后无法再访问。

```javascript
// ❌ 场景1：存了 Java wrapper，延迟使用时已被 GC
var savedObj = someJavaObj;
setTimeout(function () {
    savedObj.method();  // "Wrapper is disposed"
}, 100);

// ❌ 场景2：在拦截器链多层嵌套中存了 Java wrapper
lastRequest[tid] = request;  // Java wrapper
// 内层 proceed 执行完后，外层的 wrapper 可能已 disposed
printRequest(lastRequest[tid]);  // "Wrapper is disposed"

// ❌ 场景3：headers 对象中的值是 Java String wrapper
var headers = {};
headers[name] = request.headers().get(name);  // Java String
// 后续 console.log 拼接时静默失败，什么也不输出

// ✅ 解决方案：所有值立即 "" + 转为 JS 原生值
var info = {
    url: "" + request.url().toString(),
    headers: formatHeaders(request.headers())  // 内部也用 "" +
};
```

**规则：Java wrapper 不能跨调用栈帧存储。如果需要在后续使用，必须在当前帧立即提取为纯 JS 值。**

### 3.5 Java Callback 包装类的 GC 问题

```javascript
// ❌ 错误：callback 会被 GC 回收
overload.implementation = function (callback) {
    var wrapped = new WrappedCallback(callback);
    this.enqueue(wrapped);
};

// ✅ 正确：用 Java.retain() 阻止 GC
overload.implementation = function (callback) {
    var origCb = Java.retain(callback);
    // ...
};
```

### 3.6 `Java.registerClass` 类名必须唯一

```javascript
// ❌ 重复注册同名类会报错
var Wrapped = Java.registerClass({ name: "com.hook.MyCallback", ... });

// ✅ 用计数器保证唯一
var counter = 0;
var Wrapped = Java.registerClass({ name: "com.hook.MyCb" + (++counter), ... });
```

### 3.7 console.log("") 可能吞掉输出

```javascript
// ❌ Frida 中 console.log("") 后续行可能不输出
console.log("");
console.log("this may not appear");

// ✅ 用统一日志函数，永远不传空字符串
tsLog("--- separator ---");  // 如果需要分隔，用有内容的字符串
```

---

## 四、Native Hook 要点

### 4.1 不能放在 `Java.perform()` 内

```javascript
// ❌ 错误
Java.perform(function () {
    Process.findModuleByName(...);  // TypeError: not a function
});

// ✅ 正确
Java.perform(function () { /* Java hooks */ });
hookNativeCrypto();  // 独立执行
```

### 4.2 SO 库可能延迟加载

```javascript
function hookNative() {
    var libName = "libnative-lib.so";
    function doHook() {
        var mod = Process.findModuleByName(libName);
        if (!mod) return false;
        // 执行 hook...
        return true;
    }
    if (!doHook()) {
        var timer = setInterval(function () {
            if (doHook()) clearInterval(timer);
        }, 1000);
    }
}
```

### 4.3 JNI 函数参数读取

```javascript
Interceptor.attach(addr, {
    onEnter: function (args) {
        // args[0] = JNIEnv*, args[1] = jobject/jclass, args[2] = 第一个 Java 参数
        var env = Java.vm.getEnv();
        var str = env.getStringUtfChars(args[2], null).readUtf8String();
    }
});
```

---

## 五、调试策略

### 5.1 逐步启用 Hook

```javascript
function hookJava() {
    hookRealCall();           // 第一步
    // hookResponseBodyString();  // 第二步
    // hookWebSocket();            // 第三步
}
```

### 5.2 区分异常类型

| 现象 | 类型 | 处理方式 |
|------|------|---------|
| `[Error: xxx]` 在 Frida console | JS 异常 | try-catch 可捕获 |
| App 闪退，Frida 断开连接 | Native 崩溃 | JS 无法捕获，排查 hook 是否破坏对象状态 |
| `TypeError: not a function` | API 调用错误 | 检查上下文（如 Native API 在 Java.perform 内） |
| "Wrapper is disposed" | Java wrapper GC | 立即用 `"" +` 提取为纯 JS 值 |
| console.log 后无输出 | console.log("") 吞输出 | 用统一 tsLog 函数 |

### 5.3 Hook 点选择优先级

```
优先 hook 高层 API：
  RealCall.execute / enqueue    → 拿到完整 Request 和 Response

避免 hook 内部实现类：
  CallServerInterceptor         → 内部细节，版本间可能变化
  Exchange                      → 过于底层，不稳定

优先 hook 接口方法：
  ResponseBody.string()         → 接口层，各版本实现不同但接口稳定
```

---

## 六、通用 Hook 检查清单

编写任何 Hook 时，对照以下清单：

### 数据安全
- [ ] **Response body**：是否在 hook 中主动调用了消耗方法（string/bytes/peekBody）？改为被动拦截
- [ ] **Request body**：是否用了 `okio.Buffer` + `writeTo()` + `readUtf8()`？且只在打印时读一次？
- [ ] **body 读取次数**：是否在循环/链式调用中反复读取 body？改为只读一次

### Java Bridge
- [ ] **字符串操作**：对 Java 返回的值做 JS 操作前，是否用 `"" + value` 转为 JS string？
- [ ] **Wrapper 存储**：是否存了 Java wrapper 并在后续使用？改为立即提取纯 JS 值
- [ ] **闭包变量**：for 循环中的遍历是否用了 IIFE 捕获变量？
- [ ] **overloads 遍历**：是否遍历了所有重载？
- [ ] **Callback GC**：enqueue 的 callback 是否用了 `Java.retain()`？
- [ ] **registerClass 唯一性**：动态注册的类名是否有唯一后缀？

### 代码结构
- [ ] **打印时机**：关键信息打印是否在原始方法调用之前？（防止异常丢失）
- [ ] **统一日志**：是否用统一的 tsLog 函数？是否有 console.log("")？
- [ ] **try-catch**：hook 逻辑是否包裹在 try-catch 中？
- [ ] **Native hook 位置**：是否放在 `Java.perform()` 外面？
- [ ] **延迟加载**：SO 库是否做了延迟加载等待？

### 链式调用（拦截器链）特殊检查
- [ ] **ThreadLocal 状态**：是否用 tid 做线程隔离？
- [ ] **头完整性**：是否用头数量增长判断 request 完整性？
- [ ] **状态清理**：isOuterCall 时是否清理了所有 ThreadLocal 状态？

---

## 七、快速参考：OkHttp3 Hook 可安全调用的方法

### Request 对象（安全，只读）

| 方法 | 安全 | 说明 |
|------|:---:|------|
| `request.url()` | ✅ | 纯读取，结果需 `"" +` 转为 JS string |
| `request.method()` | ✅ | 纯读取，结果需 `"" +` 转为 JS string |
| `request.headers()` | ✅ | 纯读取，遍历时 key/value 都需 `"" +` |
| `request.body()` | ✅ | 获取引用 |
| `request.body().writeTo(buffer)` | ✅ | 复制到 buffer，不消耗原始 body |

### Response 对象

| 方法 | 安全 | 说明 |
|------|:---:|------|
| `response.code()` | ✅ | 纯读取 |
| `response.message()` | ✅ | 纯读取，结果需 `"" +` |
| `response.headers()` | ✅ | 纯读取，遍历时 key/value 都需 `"" +` |
| `response.request()` | ✅ | 纯读取 |
| `response.body()` | ✅ | 获取引用（但不调用 body 的读取方法） |
| `response.body().string()` | ❌ | **消耗 body，导致 app 崩溃** |
| `response.body().bytes()` | ❌ | **同上** |
| `response.peekBody()` | ❌ | **看似安全但会 SIGSEGV** |

### ResponseBody 被动 Hook（安全）

```javascript
// 这些是在 app 自己调用时拦截，不会导致额外消耗
hook ResponseBody.string()   → 拦截 app 的调用结果
hook ResponseBody.bytes()    → 拦截 app 的调用结果
```
