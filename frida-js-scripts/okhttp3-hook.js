function hookOkhttp3() {
    var OkHttpClient = Java.use("okhttp3.OkHttpClient");
    OkHttpClient.newCall.overload("okhttp3.Request")
        .implementation = function (request) {
        console.log("HTTP Request -> " + request.url().toString());
        var call = this.newCall(request); // 获取新的 Call 对象
        var response = call.execute(); // 调用新的 Call 对象的 execute 方法
        console.log("HTTP Response -> " + response.body().string());
        return call
    }
}

function hookOkhttp3_2() {
    console.log("[*] 开始寻找混淆后的 OkHttpClient...");

    // 1. 获取应用中所有已加载的类
    var classes = Java.enumerateLoadedClassesSync();
    var targetBuilderClass = null;
    var targetOkHttpClientClass = null;

    // 2. 遍历所有类，寻找符合特征的 Builder 类
    // 特征：类名包含 "Builder"，并且其外部类（Enclosing Class）的类加载器与它相同
    for (var i = 0; i < classes.length; i++) {
        var className = classes[i];
        if (className.indexOf("Builder") !== -1) {
            try {
                var builderClass = Java.use(className);
                // 尝试获取其外部类，如果能获取到，说明它是一个内部类
                var enclosingClass = builderClass.class.getEnclosingClass();
                if (enclosingClass) {
                    // 这里可以打印出来辅助判断，或者加入更复杂的特征判断
                    // console.log("找到可能的Builder: " + className + ", 外部类: " + enclosingClass.getName());
                    targetBuilderClass = builderClass;
                    targetOkHttpClientClass = Java.use(enclosingClass.getName());
                    console.log("[+] 找到目标类！Builder: " + className + ", OkHttpClient: " + enclosingClass.getName());
                    break;
                }
            } catch (e) {
                // 忽略找不到的类
            }
        }
    }

    // 3. 如果找到了，就可以使用 targetOkHttpClientClass 进行后续的 Hook 操作
    if (targetOkHttpClientClass) {
        console.log("[*] 成功定位，现在可以开始 Hook 了。");
        // 例如：Hook newCall 方法
        // targetOkHttpClientClass.newCall.implementation = function(request) { ... }
    } else {
        console.log("[-] 未找到目标类，请检查应用是否使用了 OkHttp。");
    }
}

function main() {
    Java.perform(function () {
        // hookOkhttp3()
        hookOkhttp3_2()
    })
}

setImmediate(main);