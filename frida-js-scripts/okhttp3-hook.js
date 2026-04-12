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
        return "<body read error>";
    }
}

function invoke(self, methodName, args) {
    switch (args.length) {
        case 0: return self[methodName]();
        case 1: return self[methodName](args[0]);
        case 2: return self[methodName](args[0], args[1]);
        case 3: return self[methodName](args[0], args[1], args[2]);
        case 4: return self[methodName](args[0], args[1], args[2], args[3]);
        default: return self[methodName](args[0], args[1], args[2], args[3], args[4]);
    }
}

function hookMethod(cls, methodName, impl) {
    if (!cls || !cls[methodName]) return;
    var overloads = cls[methodName].overloads;
    if (!overloads) return;
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            try {
                overload.implementation = function () {
                    var args = [];
                    for (var j = 0; j < arguments.length; j++) args.push(arguments[j]);
                    return impl.call(this, methodName, args);
                };
            } catch (e) {
                console.log("[-] hook " + methodName + " failed: " + e.message);
            }
        })(overloads[i]);
    }
}

function hookRequestBuilder() {
    var cls = tryUse("okhttp3.Request$Builder");
    if (!cls) return;

    hookMethod(cls, "$init", function (mn, args) {
        console.log("[Request.Builder] created");
        return invoke(this, mn, args);
    });

    hookMethod(cls, "url", function (mn, args) {
        console.log("[Request.Builder] url: " + args[0]);
        return invoke(this, mn, args);
    });

    hookMethod(cls, "method", function (mn, args) {
        var bodyStr = args[1] ? tryGetBodyString(args[1]) : null;
        console.log("[Request.Builder] method: " + args[0] +
            (bodyStr ? "\n  body: " + bodyStr.substring(0, Math.min(bodyStr.length(), 500)) : ""));
        return invoke(this, mn, args);
    });

    hookMethod(cls, "addHeader", function (mn, args) {
        console.log("[Request.Builder] addHeader: " + args[0] + " = " + args[1]);
        return invoke(this, mn, args);
    });

    hookMethod(cls, "header", function (mn, args) {
        console.log("[Request.Builder] header: " + args[0] + " = " + args[1]);
        return invoke(this, mn, args);
    });

    hookMethod(cls, "removeHeader", function (mn, args) {
        console.log("[Request.Builder] removeHeader: " + args[0]);
        return invoke(this, mn, args);
    });

    hookMethod(cls, "headers", function (mn, args) {
        console.log("[Request.Builder] headers: " + JSON.stringify(formatHeaders(args[0])));
        return invoke(this, mn, args);
    });

    hookMethod(cls, "build", function (mn, args) {
        var request = invoke(this, mn, args);
        try {
            var url = request.url().toString();
            var method = request.method();
            var headers = formatHeaders(request.headers());
            console.log("[Request.Builder] build -> " + method + " " + url);
            console.log("  headers: " + JSON.stringify(headers));
        } catch (e) {}
        return request;
    });
}

function hookResponse() {
    var cls = tryUse("okhttp3.Response");
    if (!cls) return;

    hookMethod(cls, "body", function (mn, args) {
        var body = invoke(this, mn, args);
        if (body != null) {
            try { console.log("[Response] body: " + this.request().url().toString()); }
            catch (e) { console.log("[Response] body available"); }
        }
        return body;
    });

    hookMethod(cls, "code", function (mn, args) {
        var code = invoke(this, mn, args);
        try { console.log("[Response] code: " + code + " url: " + this.request().url().toString()); }
        catch (e) { console.log("[Response] code: " + code); }
        return code;
    });

    hookMethod(cls, "headers", function (mn, args) {
        var headers = invoke(this, mn, args);
        console.log("[Response] headers: " + JSON.stringify(formatHeaders(headers)));
        return headers;
    });
}

function hookResponseBody() {
    var cls = tryUse("okhttp3.ResponseBody");
    if (!cls) return;

    hookMethod(cls, "string", function (mn, args) {
        var result = invoke(this, mn, args);
        var preview = result ? result.substring(0, Math.min(result.length(), 300)) : "";
        console.log("[ResponseBody] string() length=" + (result ? result.length() : 0) +
            "\n  preview: " + preview);
        return result;
    });

    hookMethod(cls, "bytes", function (mn, args) {
        var result = invoke(this, mn, args);
        console.log("[ResponseBody] bytes() length=" + (result ? result.length : 0));
        return result;
    });
}

function hookOkHttpClientBuilder() {
    var cls = tryUse("okhttp3.OkHttpClient$Builder");
    if (!cls) return;

    hookMethod(cls, "addInterceptor", function (mn, args) {
        try { console.log("[OkHttpClient.Builder] addInterceptor: " + args[0].getClass().getName()); }
        catch (e) { console.log("[OkHttpClient.Builder] addInterceptor"); }
        return invoke(this, mn, args);
    });

    hookMethod(cls, "addNetworkInterceptor", function (mn, args) {
        try { console.log("[OkHttpClient.Builder] addNetworkInterceptor: " + args[0].getClass().getName()); }
        catch (e) { console.log("[OkHttpClient.Builder] addNetworkInterceptor"); }
        return invoke(this, mn, args);
    });

    hookMethod(cls, "connectTimeout", function (mn, args) {
        console.log("[OkHttpClient.Builder] connectTimeout: " + args.join(", "));
        return invoke(this, mn, args);
    });

    hookMethod(cls, "readTimeout", function (mn, args) {
        console.log("[OkHttpClient.Builder] readTimeout: " + args.join(", "));
        return invoke(this, mn, args);
    });

    hookMethod(cls, "writeTimeout", function (mn, args) {
        console.log("[OkHttpClient.Builder] writeTimeout: " + args.join(", "));
        return invoke(this, mn, args);
    });

    hookMethod(cls, "certificatePinner", function (mn, args) {
        console.log("[OkHttpClient.Builder] certificatePinner: " + args[0]);
        return invoke(this, mn, args);
    });

    hookMethod(cls, "cookieJar", function (mn, args) {
        try { console.log("[OkHttpClient.Builder] cookieJar: " + args[0].getClass().getName()); }
        catch (e) { console.log("[OkHttpClient.Builder] cookieJar"); }
        return invoke(this, mn, args);
    });

    hookMethod(cls, "build", function (mn, args) {
        console.log("[OkHttpClient.Builder] build()");
        return invoke(this, mn, args);
    });
}

function hookCertificatePinner() {
    var cls = tryUse("okhttp3.CertificatePinner");
    if (!cls) return;

    hookMethod(cls, "check", function (mn, args) {
        console.log("[CertificatePinner] check hostname=" + args[0]);
        try {
            return invoke(this, mn, args);
        } catch (e) {
            console.log("[CertificatePinner] PIN FAILED: " + e.message);
            throw e;
        }
    });
}

function hookRealCall() {
    var cls = tryUse("okhttp3.internal.connection.RealCall");
    if (!cls) cls = tryUse("okhttp3.RealCall");
    if (!cls) return;

    hookMethod(cls, "execute", function (mn, args) {
        try {
            var req = this.request();
            console.log("[RealCall] execute: " + req.method() + " " + req.url().toString());
        } catch (e) {}
        var resp = invoke(this, mn, args);
        try { console.log("[RealCall] execute response: " + resp.code()); } catch (e) {}
        return resp;
    });

    hookMethod(cls, "enqueue", function (mn, args) {
        try {
            var req = this.request();
            console.log("[RealCall] enqueue: " + req.method() + " " + req.url().toString());
        } catch (e) {}
        return invoke(this, mn, args);
    });
}

function hookWebSocket() {
    var cls = tryUse("okhttp3.internal.ws.RealWebSocket");
    if (!cls) return;

    hookMethod(cls, "send", function (mn, args) {
        console.log("[WebSocket] send: " + args[0]);
        return invoke(this, mn, args);
    });
}

function hookCookieJar() {
    try {
        var impls = Java.enumerateMethods("*CookieJar*");
        if (impls && impls.length > 0) {
            console.log("[+] CookieJar implementations: " + JSON.stringify(impls));
        }
    } catch (e) {}
}

function hookJava() {
    console.log("============================================================");
    console.log("[*] OkHttp3 Hook Script Starting...");
    console.log("============================================================");

    hookRequestBuilder();
    hookResponse();
    hookResponseBody();
    hookOkHttpClientBuilder();
    hookCertificatePinner();
    hookRealCall();
    hookWebSocket();
    hookCookieJar();

    console.log("[+] All Java hooks installed");
}

function hookNativeCrypto() {
    console.log("[*] Hooking NativeCrypto JNI methods...");

    var libName = "libnative-lib.so";

    function doHook() {
        try {
            var mod = Process.findModuleByName(libName);
            if (!mod) return false;

            console.log("[+] " + libName + " base: " + mod.baseAddress);
            var exports = mod.enumerateExports();
            console.log("[+] Found " + exports.length + " exports");

            for (var i = 0; i < exports.length; i++) {
                var exp = exports[i];
                if (exp.name.indexOf("NativeCrypto") === -1 && exp.name.indexOf("native") === -1) continue;
                if (exp.type !== "function") continue;

                console.log("[+] Export: " + exp.name + " @ " + exp.address);
                attachNativeHook(exp);
            }
            return true;
        } catch (e) {
            console.log("[-] Native hook error: " + e.message);
            return false;
        }
    }

    if (!doHook()) {
        console.log("[-] " + libName + " not loaded, waiting...");
        var timer = setInterval(function () {
            if (doHook()) clearInterval(timer);
        }, 1000);
    }
}

function attachNativeHook(exp) {
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
                } else if (exp.name.indexOf("sign") !== -1 && exp.name.indexOf("verify") === -1) {
                    this.fnType = "sign";
                    this.data = env.getStringUtfChars(args[1], null).readUtf8String();
                    console.log("[Native] sign(\"" + this.data + "\")");
                }
            } catch (e) {}
        },
        onLeave: function (retval) {
            try {
                if (this.fnType === "verifySignature") {
                    console.log("[Native] verifySignature -> " + (retval.toInt32() ? "true" : "false"));
                } else if (this.fnType) {
                    console.log("[Native] " + this.fnType + " -> retval=" + retval);
                }
            } catch (e) {}
        }
    });
}

setTimeout(function () {
    Java.perform(function () {
        hookJava();
    });
    hookNativeCrypto();
}, 3000);
