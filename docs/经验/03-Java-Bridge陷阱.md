# Frida Java Bridge 陷阱

> Frida Java Bridge 中的常见陷阱：方法包装器、字符串类型、闭包变量、GC 问题等。

---

## 3.1 Java 方法包装器不是普通 JS Function

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

---

## 3.2 字符串类型混淆

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

---

## 3.3 for 循环中的闭包变量捕获

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

---

## 3.4 Java Wrapper 的 GC 问题（"Wrapper is disposed"）

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

---

## 3.5 Java Callback 包装类的 GC 问题

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

---

## 3.6 `Java.registerClass` 类名必须唯一

```javascript
// ❌ 重复注册同名类会报错
var Wrapped = Java.registerClass({ name: "com.hook.MyCallback", ... });

// ✅ 用计数器保证唯一
var counter = 0;
var Wrapped = Java.registerClass({ name: "com.hook.MyCb" + (++counter), ... });
```

---

## 3.7 console.log("") 可能吞掉输出

```javascript
// ❌ Frida 中 console.log("") 后续行可能不输出
console.log("");
console.log("this may not appear");

// ✅ 用统一日志函数，永远不传空字符串
tsLog("--- separator ---");  // 如果需要分隔，用有内容的字符串
```
