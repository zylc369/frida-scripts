# OkHttp3 Hook 可安全调用的方法

> OkHttp3 Request/Response 对象中哪些方法可以安全调用，哪些会导致崩溃。

---

## Request 对象（安全，只读）

| 方法 | 安全 | 说明 |
|------|:---:|------|
| `request.url()` | ✅ | 纯读取，结果需 `"" +` 转为 JS string |
| `request.method()` | ✅ | 纯读取，结果需 `"" +` 转为 JS string |
| `request.headers()` | ✅ | 纯读取，遍历时 key/value 都需 `"" +` |
| `request.body()` | ✅ | 获取引用 |
| `request.body().writeTo(buffer)` | ✅ | 复制到 buffer，不消耗原始 body |

---

## Response 对象

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

---

## ResponseBody 被动 Hook（安全）

```javascript
// 这些是在 app 自己调用时拦截，不会导致额外消耗
hook ResponseBody.string()   → 拦截 app 的调用结果
hook ResponseBody.bytes()    → 拦截 app 的调用结果
```
