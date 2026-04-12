"use strict";

function tryUse(className) {
    try {
        return Java.use(className);
    } catch (e) {
        console.log("[-] Class not found: " + className);
        return null;
    }
}

function formatHeaders(headers) {
    var result = {};
    if (headers) {
        var names = headers.names();
        var it = names.iterator();
        while (it.hasNext()) {
            var name = it.next();
            result[name] = headers.get(name);
        }
    }
    return result;
}

function tryGetBodyString(body) {
    if (!body) return null;
    try {
        var bytes = body.bytes();
        var StringCls = Java.use("java.lang.String");
        return StringCls.$new(bytes, "UTF-8");
    } catch (e) {
        return "<body read error: " + e.message + ">";
    }
}

function hookRequestBuilder() {
    var RequestBuilder = tryUse("okhttp3.Request$Builder");
    if (!RequestBuilder) return;

    RequestBuilder.$init.implementation = function () {
        console.log("[Request.Builder] created");
        return this.$init();
    };

    RequestBuilder.url.overload("java.lang.String").implementation = function (url) {
        console.log("[Request.Builder] url: " + url);
        return this.url(url);
    };

    RequestBuilder.method.implementation = function (method, body) {
        var bodyStr = body ? tryGetBodyString(body) : null;
        console.log("[Request.Builder] method: " + method +
            (bodyStr ? "\n  body: " + bodyStr.substring(0, Math.min(bodyStr.length(), 500)) : ""));
        return this.method(method, body);
    };

    RequestBuilder.addHeader.implementation = function (name, value) {
        console.log("[Request.Builder] addHeader: " + name + " = " + value);
        return this.addHeader(name, value);
    };

    RequestBuilder.header.implementation = function (name, value) {
        console.log("[Request.Builder] header: " + name + " = " + value);
        return this.header(name, value);
    };

    RequestBuilder.removeHeader.implementation = function (name) {
        console.log("[Request.Builder] removeHeader: " + name);
        return this.removeHeader(name);
    };

    RequestBuilder.build.implementation = function () {
        var request = this.build();
        var url = request.url().toString();
        var method = request.method();
        var headers = formatHeaders(request.headers());
        console.log("[Request.Builder] build → " + method + " " + url);
        console.log("  headers: " + JSON.stringify(headers));
        return request;
    };
}

function hookResponse() {
    var Response = tryUse("okhttp3.Response");
    if (!Response) return;

    var originalBody = Response.body;

    Response.body.implementation = function () {
        var body = originalBody.call(this);
        if (body != null) {
            console.log("[Response] body available for: " + this.request().url().toString());
        }
        return body;
    };

    Response.code.implementation = function () {
        var code = this.code();
        console.log("[Response] code: " + code + " url: " + this.request().url().toString());
        return code;
    };

    Response.headers.implementation = function () {
        var headers = this.headers();
        console.log("[Response] headers: " + JSON.stringify(formatHeaders(headers)));
        return headers;
    };
}

function hookResponseBody() {
    var ResponseBody = tryUse("okhttp3.ResponseBody");
    if (!ResponseBody) return;

    var originalString = ResponseBody.string;
    ResponseBody.string.implementation = function () {
        var result = originalString.call(this);
        var preview = result ? result.substring(0, Math.min(result.length(), 300)) : "";
        console.log("[ResponseBody] string() length=" + (result ? result.length() : 0) +
            "\n  preview: " + preview);
        return result;
    };

    var originalBytes = ResponseBody.bytes;
    ResponseBody.bytes.implementation = function () {
        var result = originalBytes.call(this);
        console.log("[ResponseBody] bytes() length=" + (result ? result.length : 0));
        return result;
    };
}

function hookOkHttpClientBuilder() {
    var Builder = tryUse("okhttp3.OkHttpClient$Builder");
    if (!Builder) return;

    Builder.addInterceptor.implementation = function (interceptor) {
        console.log("[OkHttpClient.Builder] addInterceptor: " + interceptor.getClass().getName());
        return this.addInterceptor(interceptor);
    };

    Builder.addNetworkInterceptor.implementation = function (interceptor) {
        console.log("[OkHttpClient.Builder] addNetworkInterceptor: " + interceptor.getClass().getName());
        return this.addNetworkInterceptor(interceptor);
    };

    Builder.connectTimeout.implementation = function (timeout, unit) {
        console.log("[OkHttpClient.Builder] connectTimeout: " + timeout + " " + unit);
        return this.connectTimeout(timeout, unit);
    };

    Builder.readTimeout.implementation = function (timeout, unit) {
        console.log("[OkHttpClient.Builder] readTimeout: " + timeout + " " + unit);
        return this.readTimeout(timeout, unit);
    };

    Builder.writeTimeout.implementation = function (timeout, unit) {
        console.log("[OkHttpClient.Builder] writeTimeout: " + timeout + " " + unit);
        return this.writeTimeout(timeout, unit);
    };

    Builder.certificatePinner.implementation = function (pinner) {
        console.log("[OkHttpClient.Builder] certificatePinner: " + pinner);
        return this.certificatePinner(pinner);
    };

    Builder.cookieJar.implementation = function (cookieJar) {
        console.log("[OkHttpClient.Builder] cookieJar: " + cookieJar.getClass().getName());
        return this.cookieJar(cookieJar);
    };

    Builder.build.implementation = function () {
        console.log("[OkHttpClient.Builder] build()");
        return this.build();
    };
}

function hookCertificatePinner() {
    var CertPinner = tryUse("okhttp3.CertificatePinner");
    if (!CertPinner) return;

    var originalCheck = CertPinner.check.overload("java.lang.String", "java.util.List");
    originalCheck.implementation = function (hostname, peerCertificates) {
        console.log("[CertificatePinner] check: hostname=" + hostname +
            " certs=" + peerCertificates.size());
        try {
            return originalCheck.call(this, hostname, peerCertificates);
        } catch (e) {
            console.log("[CertificatePinner] PIN FAILED: " + e.message);
            throw e;
        }
    };
}

function hookRealCall() {
    var RealCall = tryUse("okhttp3.internal.connection.RealCall");
    if (!RealCall) {
        RealCall = tryUse("okhttp3.RealCall");
    }
    if (!RealCall) return;

    var originalExecute;
    try {
        originalExecute = RealCall.execute;
        RealCall.execute.implementation = function () {
            var request = this.request();
            console.log("[RealCall] execute: " + request.method() + " " + request.url().toString());
            var response = originalExecute.call(this);
            console.log("[RealCall] execute response: " + response.code());
            return response;
        };
    } catch (e) {
        console.log("[-] Could not hook RealCall.execute: " + e.message);
    }

    var originalEnqueue;
    try {
        originalEnqueue = RealCall.enqueue;
        RealCall.enqueue.implementation = function (callback) {
            var request = this.request();
            console.log("[RealCall] enqueue: " + request.method() + " " + request.url().toString());
            return originalEnqueue.call(this, callback);
        };
    } catch (e) {
        console.log("[-] Could not hook RealCall.enqueue: " + e.message);
    }
}

function hookWebSocket() {
    var RealWebSocket = tryUse("okhttp3.internal.ws.RealWebSocket");
    if (!RealWebSocket) return;

    var originalSend = RealWebSocket.send.overload("java.lang.String");
    originalSend.implementation = function (text) {
        console.log("[WebSocket] send: " + text);
        return originalSend.call(this, text);
    };

    try {
        var onMessage = RealWebSocket.onMessage;
        console.log("[+] WebSocket.onMessage found, hooking...");
    } catch (e) {
        console.log("[-] WebSocket.onMessage hook skipped (abstract/interface)");
    }
}

function hookCookieJar() {
    var CookieJar = tryUse("okhttp3.CookieJar");
    if (!CookieJar) return;

    var implementations = Java.enumerateMethods("*CookieJar*");
    if (implementations && implementations.length > 0) {
        console.log("[+] CookieJar implementations found: " + JSON.stringify(implementations));
    }
}

function hookNativeCrypto() {
    console.log("[*] Hooking NativeCrypto JNI methods via Interceptor...");

    var nativeLibName = "libnative-lib.so";
    var baseAddr = Module.findBaseAddress(nativeLibName);
    if (!baseAddr) {
        console.log("[-] " + nativeLibName + " not loaded yet, setting up delayed hook...");
        var interval = setInterval(function () {
            baseAddr = Module.findBaseAddress(nativeLibName);
            if (baseAddr) {
                clearInterval(interval);
                doHookNative(baseAddr, nativeLibName);
            }
        }, 1000);
    } else {
        doHookNative(baseAddr, nativeLibName);
    }
}

function doHookNative(baseAddr, libName) {
    console.log("[+] " + libName + " base: " + baseAddr);

    var exports = Module.enumerateExports(libName);
    console.log("[+] Found " + exports.length + " exports in " + libName);

    exports.forEach(function (exp) {
        if (exp.name.indexOf("NativeCrypto") !== -1 || exp.name.indexOf("native") !== -1) {
            console.log("[+] Export: " + exp.name + " @ " + exp.address);

            Interceptor.attach(exp.address, {
                onEnter: function (args) {
                    this.args = [];
                    for (var i = 0; i < args.length; i++) {
                        this.args.push(args[i]);
                    }

                    if (exp.name.indexOf("encrypt") !== -1) {
                        var env = Java.vm.getEnv();
                        var input = env.getStringUtfChars(args[1], null).readUtf8String();
                        console.log("[Native] encrypt(\"" + input + "\")");
                    } else if (exp.name.indexOf("decrypt") !== -1) {
                        var env = Java.vm.getEnv();
                        var input = env.getStringUtfChars(args[1], null).readUtf8String();
                        console.log("[Native] decrypt(\"" + input + "\")");
                    } else if (exp.name.indexOf("verifySignature") !== -1) {
                        var env = Java.vm.getEnv();
                        var data = env.getStringUtfChars(args[1], null).readUtf8String();
                        var sig = env.getStringUtfChars(args[2], null).readUtf8String();
                        console.log("[Native] verifySignature(data=\"" + data + "\", sig=\"" + sig + "\")");
                    } else if (exp.name.indexOf("sign") !== -1) {
                        var env = Java.vm.getEnv();
                        var data = env.getStringUtfChars(args[1], null).readUtf8String();
                        console.log("[Native] sign(\"" + data + "\")");
                    }
                },
                onLeave: function (retval) {
                    var fnName = exp.name.split("_").pop();
                    if (exp.name.indexOf("verifySignature") !== -1) {
                        console.log("[Native] verifySignature → " + (retval.toInt32() ? "true" : "false"));
                    } else {
                        console.log("[Native] " + fnName + " → retval=" + retval);
                    }
                }
            });
        }
    });
}

function hookAll() {
    console.log("=".repeat(60));
    console.log("[*] OkHttp3 + Native Hook Script Starting...");
    console.log("=".repeat(60));

    hookRequestBuilder();
    hookResponse();
    hookResponseBody();
    hookOkHttpClientBuilder();
    hookCertificatePinner();
    hookRealCall();
    hookWebSocket();
    hookCookieJar();

    hookNativeCrypto();

    console.log("[+] All hooks installed");
}

setTimeout(function () {
    Java.perform(function () {
        hookAll();
    });
}, 3000);
