function hookOkhttp3(){
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

function main(){
    Java.perform(function () {
        hookOkhttp3()
    })
}

setImmediate(main);