# Frida Hook 开发经验总结

> 基于 OkHttp3 Hook 开发过程中的踩坑经验整理，目标是下次编写 Hook 代码时不再踩同样的坑。

---

## 一、核心原则：不破坏被 Hook 对象的状态

这是最重要的一条规则，也是本次开发过程中反复崩溃的根因。

### 规则

**永远不要在 hook 中消耗一次性资源。**

### 典型反面案例：OkHttp ResponseBody

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

### 正确策略：被动拦截

不要主动去读，而是 **hook 消费端**，等 app 自己调用时拦截返回值：

```
错误做法：
  hook RealCall.execute → 主动调用 body.string() 打印 → 崩溃

正确做法：
  hook RealCall.execute → 只打印 request/response headers（不碰 body）
  hook ResponseBody.string() → 等app自己调用时拦截返回值打印
  hook ResponseBody.bytes() → 同上
```

### RequestBody 为什么可以主动读？

```
RequestBody 可以用 okio.Buffer 读取：
  var buffer = Buffer.$new();
  reqBody.writeTo(buffer);   // 写入副本，不消耗原始 body
  return buffer.readUtf8();  // 安全读取
```

因为 `writeTo()` 是将 body 内容**复制**到 buffer，原始 body 不受影响。这与 ResponseBody 的读取方式有本质区别。

### 判断标准

```
能否主动调用某方法？
  ├── 该方法是否会修改对象状态？ → 不能
  ├── 该方法是否消耗底层资源（流、buffer、连接）？ → 不能
  ├── 该方法是否有 side effect？ → 谨慎
  └── 该方法是否是纯读取/复制？ → 可以
```

---

## 二、Hook 架构模式

### 2.1 主动拦截 vs 被动拦截

| 场景 | 模式 | 说明 |
|------|------|------|
| Request headers | 主动拦截 | 在 RealCall hook 中直接读取，headers 是纯数据，无 side effect |
| Request body | 主动拦截 | 用 okio.Buffer 复制读取，安全 |
| Response headers | 主动拦截 | 同 request headers |
| Response body | **被动拦截** | hook ResponseBody.string()/bytes()，不主动消耗 |
| Native 函数参数/返回值 | 被动拦截 | Interceptor.attach 的 onEnter/onLeave |

### 2.2 防御性编程模板

```javascript
// hook 函数的标准模板
function hookSomething() {
    var cls = tryUse("com.example.TargetClass");
    if (!cls) return;  // 类不存在就跳过，不报错

    var overloads = cls.targetMethod.overloads;
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            overload.implementation = function () {
                // 1. 先调用原始方法
                var result = this.targetMethod.apply(this, arguments);

                // 2. 在 try-catch 中做 hook 逻辑
                try {
                    // 打印/修改 result
                } catch (e) {
                    console.log("[hook error] " + e.message);
                }

                // 3. 返回结果（确保即使 hook 逻辑出错也能返回）
                return result;
            };
        })(overloads[i]);
    }
}
```

关键点：
1. **先调用原始方法**，确保 app 逻辑不受影响
2. **hook 逻辑包裹在 try-catch 中**，防止 JS 异常阻断执行流
3. **return 放在 try-catch 外面**，确保总是返回

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
// 或用 arguments
var result = this.someMethod(arguments[0], arguments[1]);
```

Frida 包装的 Java 方法是特殊对象，不是 `Function` 的实例。

### 3.2 字符串类型混淆

Frida 中 Java String 和 JS String 的边界模糊，容易出错：

```javascript
// Java 方法返回的 String，Frida 可能包装为 Java 对象或自动转为 JS string
var str = someJavaObj.toString();

// ❌ 不确定时不要假设类型
str.length()   // Java String 方法？还是 JS 会报错？
str.length     // JS 属性？还是 Java field？

// ✅ 安全做法：强制转为 JS string
var str = "" + someJavaObj.toString();
var len = str.length;  // JS 属性，100% 安全
var preview = str.substring(0, Math.min(len, 2000));  // JS 方法，100% 安全
```

**规则：需要做 JS 字符串操作时，先用 `"" + value` 强制转为 JS string。**

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

### 3.4 Java Callback 包装类的 GC 问题

```javascript
// ❌ 错误：callback 会被 GC 回收，后续调用报 "Wrapper is disposed"
overload.implementation = function (callback) {
    var wrapped = new WrappedCallback(callback);
    this.enqueue(wrapped);
    // wrapped 可能被 GC
};

// ✅ 正确：用 Java.retain() 阻止 GC
overload.implementation = function (callback) {
    var origCb = Java.retain(callback);  // 保留原始 callback
    var Wrapped = Java.registerClass({
        name: "com.hook.WrappedCb" + (++counter),  // 唯一类名
        implements: [Callback],
        methods: { /* ... */ }
    });
    this.enqueue(Wrapped.$new());
};
```

### 3.5 `Java.registerClass` 类名必须唯一

```javascript
// ❌ 重复注册同名类会报错
var Wrapped = Java.registerClass({ name: "com.hook.MyCallback", ... });
// 第二次调用就报错

// ✅ 用计数器保证唯一
var counter = 0;
var Wrapped = Java.registerClass({ name: "com.hook.MyCb" + (++counter), ... });
```

---

## 四、Native Hook 要点

### 4.1 不能放在 `Java.perform()` 内

```javascript
// ❌ 错误：Native API 在 Java.perform 内不可用
Java.perform(function () {
    Process.findModuleByName(...);  // TypeError: not a function
});

// ✅ 正确：放在 Java.perform 外面
Java.perform(function () {
    // Java hooks...
});

// Native hooks 独立执行
hookNativeCrypto();
```

`Java.perform()` 创建的是 Java 线程上下文，Native API（`Process`, `Module`, `Interceptor`）是 Frida 全局 API，不需要也不应该在 Java 上下文中调用。

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
        console.log("[-] " + libName + " not loaded, waiting...");
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
        // args[0] = JNIEnv*
        // args[1] = jobject (this) 或 jclass
        // args[2] = 第一个 Java 参数
        // args[3] = 第二个 Java 参数
        var env = Java.vm.getEnv();
        var str = env.getStringUtfChars(args[2], null).readUtf8String();
    }
});
```

---

## 五、调试策略

### 5.1 逐步启用 Hook

不要一次性挂载所有 hook，出问题时无法定位。应该：

```javascript
function hookJava() {
    // 先只开一个，确认没问题再加下一个
    hookRealCall();          // 第一步
    // hookResponseBodyString();  // 第二步
    // hookWebSocket();            // 第三步
}
```

### 5.2 区分 JS 异常和 Native 崩溃

| 现象 | 类型 | 处理方式 |
|------|------|---------|
| `[Error: xxx]` 输出在 Frida console | JS 异常 | try-catch 可捕获 |
| App 闪退，Frida 断开连接 | Native 崩溃 (SIGSEGV等) | JS 无法捕获，需排查 hook 是否破坏了对象状态 |
| `TypeError: not a function` | Frida API 调用错误 | 检查是否在错误的上下文中调用（如 Native API 在 Java.perform 内） |

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

## 六、OkHttp3 Hook 完整检查清单

编写 OkHttp3 hook 时，对照以下清单：

- [ ] **Response body**：是否在 hook 中主动调用了 `body.string()` / `body.bytes()` / `peekBody()`？如果是，改为 hook `ResponseBody.string()` 被动拦截
- [ ] **Request body**：读取时是否用了 `okio.Buffer` + `writeTo()` + `readUtf8()`？
- [ ] **字符串操作**：对 Java 返回的字符串做 JS 操作前，是否用 `"" + value` 转为 JS string？
- [ ] **闭包变量**：for 循环中的 `overloads` 遍历是否用了 IIFE 捕获变量？
- [ ] **Callback GC**：enqueue 的 callback 是否用了 `Java.retain()`？
- [ ] **registerClass 唯一性**：动态注册的类名是否有唯一后缀？
- [ ] **overloads 遍历**：是否遍历了所有重载，而不是只 hook 默认签名？
- [ ] **try-catch**：hook 逻辑是否包裹在 try-catch 中，且 return 在 catch 之外？
- [ ] **Native hook 位置**：是否放在 `Java.perform()` 外面？
- [ ] **延迟加载**：SO 库是否做了延迟加载等待？

---

## 七、快速参考：OkHttp3 Hook 可安全调用的方法

### Request 对象（安全，只读）

| 方法 | 安全 | 说明 |
|------|:---:|------|
| `request.url()` | ✅ | 纯读取 |
| `request.method()` | ✅ | 纯读取 |
| `request.headers()` | ✅ | 纯读取 |
| `request.body()` | ✅ | 获取引用 |
| `request.body().writeTo(buffer)` | ✅ | 复制到 buffer，不消耗原始 body |

### Response 对象

| 方法 | 安全 | 说明 |
|------|:---:|------|
| `response.code()` | ✅ | 纯读取 |
| `response.message()` | ✅ | 纯读取 |
| `response.headers()` | ✅ | 纯读取 |
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
