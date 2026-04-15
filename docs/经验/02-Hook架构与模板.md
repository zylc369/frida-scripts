# Hook 架构模式

> 主动拦截 vs 被动拦截策略、标准 Hook 模板、拦截器链 Hook 模式。

---

## 主动拦截 vs 被动拦截

| 场景 | 模式 | 说明 |
|------|------|------|
| Request headers | 主动拦截 | 在 hook 中直接读取，headers 是纯数据，无 side effect |
| Request body | 主动拦截 | 用 okio.Buffer 复制读取，**但只在最终打印时读一次** |
| Response headers | 主动拦截 | 同 request headers |
| Response body | **被动拦截** | hook ResponseBody.string()/bytes()，不主动消耗 |
| Native 函数参数/返回值 | 被动拦截 | Interceptor.attach 的 onEnter/onLeave |

---

## 标准 Hook 模板（修订版）

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

---

## 链式调用（拦截器链）Hook 模式

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
