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

function readRequestBody(request) {
    try {
        var reqBody = request.body();
        if (reqBody == null) return "";
        var Buffer = Java.use("okio.Buffer");
        var buffer = Buffer.$new();
        reqBody.writeTo(buffer);
        return buffer.readUtf8();
    } catch (e) {
        return "";
    }
}

function printRequest(request) {
    try {
        var url = request.url().toString();
        var method = request.method();
        var headers = formatHeaders(request.headers());
        var bodyStr = readRequestBody(request);

        console.log("");
        console.log(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>");
        console.log("[Request] " + method + " " + url);
        console.log("--------------------------------------------------------");
        var keys = Object.keys(headers);
        for (var i = 0; i < keys.length; i++) {
            console.log("  " + keys[i] + ": " + headers[keys[i]]);
        }
        if (bodyStr && bodyStr.length > 0) {
            console.log("--------------------------------------------------------");
            var bodyLen = bodyStr.length;
            console.log("  Body (" + bodyLen + "): " +
                bodyStr.substring(0, Math.min(bodyLen, 2000)));
        }
        console.log(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>");
    } catch (e) {
        console.log("[Request print error: " + e.message + "]");
    }
}

function printResponseHeaders(response) {
    try {
        var request = response.request();
        var url = request.url().toString();
        var method = request.method();
        var code = response.code();
        var msg = response.message();
        var headers = formatHeaders(response.headers());

        console.log("");
        console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
        console.log("[Response] " + code + " " + msg + " (" + method + " " + url + ")");
        console.log("--------------------------------------------------------");
        var keys = Object.keys(headers);
        for (var i = 0; i < keys.length; i++) {
            console.log("  " + keys[i] + ": " + headers[keys[i]]);
        }
        console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
    } catch (e) {
        console.log("[Response headers print error: " + e.message + "]");
    }
}

function hookResponseBodyString() {
    var ResponseBody = tryUse("okhttp3.ResponseBody");
    if (!ResponseBody) return;

    var overloads = ResponseBody.string.overloads;
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            overload.implementation = function () {
                var result = this.string();
                try {
                    var str = result ? "" + result : "";
                    var len = str.length;
                    var preview = str.substring(0, Math.min(len, 2000));
                    console.log("");
                    console.log("<<<<<<<<<<<<<<<< [ResponseBody] <<<<<<<<<<<<<<<<<<<<<<<<");
                    console.log("  Body (" + len + "): " + preview);
                    console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
                } catch (e) {}
                return result;
            };
        })(overloads[i]);
    }
}

function hookResponseBodyBytes() {
    var ResponseBody = tryUse("okhttp3.ResponseBody");
    if (!ResponseBody) return;

    var overloads = ResponseBody.bytes.overloads;
    for (var i = 0; i < overloads.length; i++) {
        (function (overload) {
            overload.implementation = function () {
                var result = this.bytes();
                try {
                    var len = result ? result.length : 0;
                    console.log("[ResponseBody.bytes] length=" + len);
                } catch (e) {}
                return result;
            };
        })(overloads[i]);
    }
}

var cbCounter = 0;

function hookRealCall() {
    var cls = tryUse("okhttp3.internal.connection.RealCall");
    if (!cls) cls = tryUse("okhttp3.RealCall");
    if (!cls) return;

    var execOv = cls.execute.overloads;
    for (var i = 0; i < execOv.length; i++) {
        (function (overload) {
            overload.implementation = function () {
                var resp = this.execute();
                printRequest(resp.request());
                printResponseHeaders(resp);
                return resp;
            };
        })(execOv[i]);
    }

    var enqOv = cls.enqueue.overloads;
    for (var i = 0; i < enqOv.length; i++) {
        (function (overload) {
            overload.implementation = function (callback) {
                var origCb = Java.retain(callback);
                var idx = ++cbCounter;
                var Callback = Java.use("okhttp3.Callback");

                var Wrapped = Java.registerClass({
                    name: "com.hook.OkCb" + idx,
                    implements: [Callback],
                    methods: {
                        onResponse: function (call, response) {
                            try {
                                printRequest(response.request());
                                printResponseHeaders(response);
                            } catch (e) {
                                console.log("[hook onResponse print error: " + e.message + "]");
                            }
                            origCb.onResponse(call, response);
                        },
                        onFailure: function (call, e) {
                            try {
                                var req = call.request();
                                console.log("");
                                console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
                                console.log("[Failure] " + req.method() + " " + req.url().toString());
                                console.log("  Error: " + e.getMessage());
                                console.log("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<");
                            } catch (ex) {}
                            origCb.onFailure(call, e);
                        }
                    }
                });

                return this.enqueue(Wrapped.$new());
            };
        })(enqOv[i]);
    }
}

function hookWebSocket() {
    var cls = tryUse("okhttp3.internal.ws.RealWebSocket");
    if (!cls) return;

    var ov = cls.send.overloads;
    for (var i = 0; i < ov.length; i++) {
        (function (overload) {
            overload.implementation = function (text) {
                console.log("[WebSocket TX] " + text);
                return this.send(text);
            };
        })(ov[i]);
    }
}

function hookNativeCrypto() {
    console.log("[*] Hooking NativeCrypto JNI methods...");

    var libName = "libnative-lib.so";

    function doHook() {
        var mod = Process.findModuleByName(libName);
        if (!mod) return false;

        console.log("[+] " + libName + " base: " + mod.baseAddress);
        var exports = mod.enumerateExports();
        console.log("[+] Found " + exports.length + " exports");

        for (var i = 0; i < exports.length; i++) {
            var exp = exports[i];
            if (exp.type !== "function") continue;
            if (exp.name.indexOf("NativeCrypto") === -1 && exp.name.indexOf("native_") === -1) continue;

            console.log("[+] Export: " + exp.name + " @ " + exp.address);

            (function (exportName, exportAddr) {
                Interceptor.attach(exportAddr, {
                    onEnter: function (args) {
                        try {
                            var env = Java.vm.getEnv();
                            if (exportName.indexOf("encrypt") !== -1) {
                                this.fnType = "encrypt";
                                this.input = env.getStringUtfChars(args[1], null).readUtf8String();
                                console.log("[Native] encrypt(\"" + this.input + "\")");
                            } else if (exportName.indexOf("decrypt") !== -1) {
                                this.fnType = "decrypt";
                                this.input = env.getStringUtfChars(args[1], null).readUtf8String();
                                console.log("[Native] decrypt(\"" + this.input + "\")");
                            } else if (exportName.indexOf("verifySignature") !== -1) {
                                this.fnType = "verifySignature";
                                this.data = env.getStringUtfChars(args[1], null).readUtf8String();
                                this.sig = env.getStringUtfChars(args[2], null).readUtf8String();
                                console.log("[Native] verifySignature(data=\"" + this.data + "\", sig=\"" + this.sig + "\")");
                            } else if (exportName.indexOf("sign") !== -1 && exportName.indexOf("verify") === -1) {
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
            })(exp.name, exp.address);
        }
        return true;
    }

    try {
        if (!doHook()) {
            console.log("[-] " + libName + " not loaded, waiting...");
            var timer = setInterval(function () {
                try { if (doHook()) clearInterval(timer); } catch (e) { clearInterval(timer); }
            }, 1000);
        }
    } catch (e) {
        console.log("[-] Native hook error: " + e.message);
    }
}

function hookJava() {
    console.log("============================================================");
    console.log("[*] OkHttp3 + Native Hook Script Starting...");
    console.log("============================================================");

    hookRealCall();
    hookResponseBodyString();
    hookResponseBodyBytes();
    hookWebSocket();

    console.log("[+] All hooks installed");
}

setTimeout(function () {
    Java.perform(function () {
        hookJava();
    });
    hookNativeCrypto();
}, 3000);
