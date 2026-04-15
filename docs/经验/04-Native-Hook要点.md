# Native Hook 要点

> Native 层 Hook 的注意事项：API 上下文、SO 延迟加载、JNI 参数读取。

---

## 4.1 不能放在 `Java.perform()` 内

```javascript
// ❌ 错误
Java.perform(function () {
    Process.findModuleByName(...);  // TypeError: not a function
});

// ✅ 正确
Java.perform(function () { /* Java hooks */ });
hookNativeCrypto();  // 独立执行
```

---

## 4.2 SO 库可能延迟加载

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

---

## 4.3 JNI 函数参数读取

```javascript
Interceptor.attach(addr, {
    onEnter: function (args) {
        // args[0] = JNIEnv*, args[1] = jobject/jclass, args[2] = 第一个 Java 参数
        var env = Java.vm.getEnv();
        var str = env.getStringUtfChars(args[2], null).readUtf8String();
    }
});
```
