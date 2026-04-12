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
    if (!headers) return {};
    var result = {};
    try {
        var names = headers.names();
        var it = names.iterator();
        while (it.hasNext()) {
            var name = it.next();
            result[name] = headers.get(name);
        }
    } catch (e) {}
    return result;
}

function tryGetBodyString(body) {
    if (!body) return null;
    try {
        var bytes = body.bytes();
        return Java.use("java.lang.String").$new(bytes, "UTF-8");
    } catch (e) {
        return "<body read error: " + e.message + ">";
    }
}

function hookAllOverloads(cls, methodName, impl) {
    if (!cls || !cls[methodName]) return;
    var method = cls[methodName];
    if (!method || !method.overloads) return;

    var overloads = method.overloads;
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            try {
                var paramTypes = overload.argumentTypes.map(function (t) { return t.className; });
                overload.implementation = function () {
                    return impl.apply(this, [overload, paramTypes, Array.prototype.slice.call(arguments)]);
                };
            } catch (e) {
                console.log("[-] hookAllOverloads(" + methodName + "(" +
                    overload.argumentTypes.map(function (t) { return t.className; }).join(", ") +
                    ")) failed: " + e.message);
            }
        })(overloads[i]);
    }
}

function safeHookAllOverloads(cls, methodName, impl) {
    try {
        hookAllOverloads(cls, methodName, impl);
    } catch (e) {
        console.log("[-] safeHookAllOverloads(" + methodName + "): " + e.message);
    }
}

function hookRequestBuilder() {
    var RequestBuilder = tryUse("okhttp3.Request$Builder");
    if (!RequestBuilder) return;

    safeHookAllOverloads(RequestBuilder, "$init", function (original, paramTypes, args) {
        if (paramTypes.length === 0) {
            console.log("[Request.Builder] created");
        } else {
            console.log("[Request.Builder] created from: " + paramTypes.join(", "));
        }
        return original.apply(this, args);
    });

    safeHookAllOverloads(RequestBuilder, "url", function (original, paramTypes, args) {
        console.log("[Request.Builder] url: " + args[0]);
        return original.apply(this, args);
    });

    safeHookAllOverloads(RequestBuilder, "method", function (original, paramTypes, args) {
        var bodyStr = args[1] ? tryGetBodyString(args[1]) : null;
        console.log("[Request.Builder] method: " + args[0] +
            (bodyStr ? "\n  body: " + bodyStr.substring(0, Math.min(bodyStr.length(), 500)) : ""));
        return original.apply(this, args);
    });

    safeHookAllOverloads(RequestBuilder, "addHeader", function (original, paramTypes, args) {
        console.log("[Request.Builder] addHeader: " + args[0] + " = " + args[1]);
        return original.apply(this, args);
    });

    safeHookAllOverloads(RequestBuilder, "header", function (original, paramTypes, args) {
        console.log("[Request.Builder] header: " + args[0] + " = " + args[1]);
        return original.apply(this, args);
    });

    safeHookAllOverloads(RequestBuilder, "removeHeader", function (original, paramTypes, args) {
        console.log("[Request.Builder] removeHeader: " + args[0]);
        return original.apply(this, args);
    });

    safeHookAllOverloads(RequestBuilder, "headers", function (original, paramTypes, args) {
        console.log("[Request.Builder] headers: " + JSON.stringify(formatHeaders(args[0])));
        return original.apply(this, args);
    });

    safeHookAllOverloads(RequestBuilder, "build", function (original, paramTypes, args) {
        var request = original.apply(this, args);
        try {
            var url = request.url().toString();
            var method = request.method();
            var headers = formatHeaders(request.headers());
            console.log("[Request.Builder] build -> " + method + " " + url);
            console.log("  headers: " + JSON.stringify(headers));
        } catch (e) {
            console.log("[Request.Builder] build (headers parse error)");
        }
        return request;
    });
}

function hookResponse() {
    var Response = tryUse("okhttp3.Response");
    if (!Response) return;

    safeHookAllOverloads(Response, "body", function (original, paramTypes, args) {
        var body = original.apply(this, args);
        if (body != null) {
            try {
                console.log("[Response] body available for: " + this.request().url().toString());
            } catch (e) {
                console.log("[Response] body available");
            }
        }
        return body;
    });

    safeHookAllOverloads(Response, "code", function (original, paramTypes, args) {
        var code = original.apply(this, args);
        try {
            console.log("[Response] code: " + code + " url: " + this.request().url().toString());
        } catch (e) {
            console.log("[Response] code: " + code);
        }
        return code;
    });

    safeHookAllOverloads(Response, "headers", function (original, paramTypes, args) {
        var headers = original.apply(this, args);
        console.log("[Response] headers: " + JSON.stringify(formatHeaders(headers)));
        return headers;
    });
}

function hookResponseBody() {
    var ResponseBody = tryUse("okhttp3.ResponseBody");
    if (!ResponseBody) return;

    safeHookAllOverloads(ResponseBody, "string", function (original, paramTypes, args) {
        var result = original.apply(this, args);
        var preview = result ? result.substring(0, Math.min(result.length(), 300)) : "";
        console.log("[ResponseBody] string() length=" + (result ? result.length() : 0) +
            "\n  preview: " + preview);
        return result;
    });

    safeHookAllOverloads(ResponseBody, "bytes", function (original, paramTypes, args) {
        var result = original.apply(this, args);
        console.log("[ResponseBody] bytes() length=" + (result ? result.length : 0));
        return result;
    });
}

function hookOkHttpClientBuilder() {
    var Builder = tryUse("okhttp3.OkHttpClient$Builder");
    if (!Builder) return;

    safeHookAllOverloads(Builder, "addInterceptor", function (original, paramTypes, args) {
        console.log("[OkHttpClient.Builder] addInterceptor: " + args[0].getClass().getName());
        return original.apply(this, args);
    });

    safeHookAllOverloads(Builder, "addNetworkInterceptor", function (original, paramTypes, args) {
        console.log("[OkHttpClient.Builder] addNetworkInterceptor: " + args[0].getClass().getName());
        return original.apply(this, args);
    });

    safeHookAllOverloads(Builder, "connectTimeout", function (original, paramTypes, args) {
        console.log("[OkHttpClient.Builder] connectTimeout: " + Array.prototype.slice.call(args).join(", "));
        return original.apply(this, args);
    });

    safeHookAllOverloads(Builder, "readTimeout", function (original, paramTypes, args) {
        console.log("[OkHttpClient.Builder] readTimeout: " + Array.prototype.slice.call(args).join(", "));
        return original.apply(this, args);
    });

    safeHookAllOverloads(Builder, "writeTimeout", function (original, paramTypes, args) {
        console.log("[OkHttpClient.Builder] writeTimeout: " + Array.prototype.slice.call(args).join(", "));
        return original.apply(this, args);
    });

    safeHookAllOverloads(Builder, "certificatePinner", function (original, paramTypes, args) {
        console.log("[OkHttpClient.Builder] certificatePinner: " + args[0]);
        return original.apply(this, args);
    });

    safeHookAllOverloads(Builder, "cookieJar", function (original, paramTypes, args) {
        console.log("[OkHttpClient.Builder] cookieJar: " + args[0].getClass().getName());
        return original.apply(this, args);
    });

    safeHookAllOverloads(Builder, "build", function (original, paramTypes, args) {
        console.log("[OkHttpClient.Builder] build()");
        return original.apply(this, args);
    });
}

function hookCertificatePinner() {
    var CertPinner = tryUse("okhttp3.CertificatePinner");
    if (!CertPinner) return;

    safeHookAllOverloads(CertPinner, "check", function (original, paramTypes, args) {
        console.log("[CertificatePinner] check(" + paramTypes.join(", ") + "): hostname=" + args[0]);
        try {
            return original.apply(this, args);
        } catch (e) {
            console.log("[CertificatePinner] PIN FAILED: " + e.message);
            throw e;
        }
    });
}

function hookRealCall() {
    var RealCall = tryUse("okhttp3.internal.connection.RealCall");
    if (!RealCall) {
        RealCall = tryUse("okhttp3.RealCall");
    }
    if (!RealCall) return;

    safeHookAllOverloads(RealCall, "execute", function (original, paramTypes, args) {
        try {
            var request = this.request();
            console.log("[RealCall] execute: " + request.method() + " " + request.url().toString());
        } catch (e) {
            console.log("[RealCall] execute");
        }
        var response = original.apply(this, args);
        try {
            console.log("[RealCall] execute response: " + response.code());
        } catch (e) {}
        return response;
    });

    safeHookAllOverloads(RealCall, "enqueue", function (original, paramTypes, args) {
        try {
            var request = this.request();
            console.log("[RealCall] enqueue: " + request.method() + " " + request.url().toString());
        } catch (e) {
            console.log("[RealCall] enqueue");
        }
        return original.apply(this, args);
    });
}

function hookWebSocket() {
    var RealWebSocket = tryUse("okhttp3.internal.ws.RealWebSocket");
    if (!RealWebSocket) return;

    safeHookAllOverloads(RealWebSocket, "send", function (original, paramTypes, args) {
        console.log("[WebSocket] send: " + args[0]);
        return original.apply(this, args);
    });
}

function hookCookieJar() {
    try {
        var implementations = Java.enumerateMethods("*CookieJar*");
        if (implementations && implementations.length > 0) {
            console.log("[+] CookieJar implementations: " + JSON.stringify(implementations));
        }
    } catch (e) {}
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
                doHookNative(nativeLibName);
            }
        }, 1000);
    } else {
        doHookNative(nativeLibName);
    }
}

function doHookNative(libName) {
    var baseAddr = Module.findBaseAddress(libName);
    console.log("[+] " + libName + " base: " + baseAddr);

    var exports = Module.enumerateExports(libName);
    console.log("[+] Found " + exports.length + " exports in " + libName);

    exports.forEach(function (exp) {
        if (exp.name.indexOf("NativeCrypto") === -1 && exp.name.indexOf("native") === -1) return;
        if (exp.type !== "function") return;

        console.log("[+] Export: " + exp.name + " @ " + exp.address);

        Interceptor.attach(exp.address, {
            onEnter: function (args) {
                try {
                    var env = Java.vm.getEnv();
                    if (exp.name.indexOf("encrypt") !== -1) {
                        this.fnType = "encrypt";
                        this.input = env.getStringUtfChars(args[1], null).readUtf8String();
                        console.log("[Native] encrypt(\"" + this.input + "\")");
                    } else if (exp.name.indexOf("decrypt") !== -1) {
                        this.fnType = "decrypt";
                        this.input = env.getStringUtfChars(args[1], null).readUtf8String();
                        console.log("[Native] decrypt(\"" + this.input + "\")");
                    } else if (exp.name.indexOf("verifySignature") !== -1) {
                        this.fnType = "verifySignature";
                        this.data = env.getStringUtfChars(args[1], null).readUtf8String();
                        this.sig = env.getStringUtfChars(args[2], null).readUtf8String();
                        console.log("[Native] verifySignature(data=\"" + this.data + "\", sig=\"" + this.sig + "\")");
                    } else if (exp.name.indexOf("sign") !== -1) {
                        this.fnType = "sign";
                        this.data = env.getStringUtfChars(args[1], null).readUtf8String();
                        console.log("[Native] sign(\"" + this.data + "\")");
                    }
                } catch (e) {
                    console.log("[Native] onEnter error: " + e.message);
                }
            },
            onLeave: function (retval) {
                if (this.fnType === "verifySignature") {
                    console.log("[Native] verifySignature -> " + (retval.toInt32() ? "true" : "false"));
                } else if (this.fnType) {
                    console.log("[Native] " + this.fnType + " -> retval=" + retval);
                }
            }
        });
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
