// 使用 Frida 的 Java 异步 API，避免直接修改方法实现
function hookOkhttp3_Final() {
    Java.perform(function() {
        // 使用 Java.choose 来实时监控已创建的实例
        var RequestBuilder = Java.use("okhttp3.Request$Builder");

        // Hook 构造函数而不是方法
        RequestBuilder.$init.implementation = function() {
            console.log("[*] Request.Builder created");
            return this.$init();
        };

        // Hook build 方法
        RequestBuilder.build.implementation = function() {
            var request = this.build();
            var url = request.url().toString();
            console.log("[Request] Built URL: " + url);
            return request;
        };

        // Hook Response 的 body 方法（只打印，不消费）
        var Response = Java.use("okhttp3.Response");
        var originalBody = Response.body;
        Response.body.implementation = function() {
            var body = originalBody.call(this);
            if (body != null) {
                console.log("[Response] Body available");
                // 注意：不要在这里调用 body.string()，会消费掉 response body
            }
            return body;
        };

        console.log("[+] Final hooks installed");
    });
}

setImmediate(hookOkhttp3_Final);