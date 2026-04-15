# AGENTS.md

## Project Overview

Frida scripts for Android security testing. Three components:

- `frida-js-scripts/` — Frida JS hook scripts (e.g. `okhttp3-hook.js`)
- `python-scripts/` — Python tooling: `start-frida.py` launches frida-server on Android via ADB; optional PySide6 GUI mode (`--gui`)
- `android-security-test-app/` — Full Android test app (Java + Gradle, minSdk 28) that exercises OkHttp3, JNI native crypto, and WebSocket. Used as a hook target.

## Commands

```bash
# Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # frida, frida-tools, PySide6

# Run frida-server launcher (CLI mode)
python python-scripts/start-frida.py -s <device_serial>

# Run frida-server launcher (GUI mode)
python python-scripts/start-frida.py --gui

# Run hook script against the test app
frida -U -f com.test.fridahook -l frida-js-scripts/okhttp3-hook.js

# Android app build (from android-security-test-app/)
./gradlew assembleDebug
```

## Architecture

### `python-scripts/`
- Entry: `start-frida.py`
- `library/` — ADB wrapper, config, logging, frida-server downloader
- `gui/` — PySide6 GUI: app list, script injection, device management

### `android-security-test-app/`
- Package: `com.test.fridahook`
- UI: DrawerLayout + NavigationView, 4 fragments (Network, Native, WebSocket, Settings)
- Network: OkHttp 4.12.0 with custom interceptors, cookie jar, cert pinning
- Native: JNI layer (`libnative-lib.so`) — XOR encrypt/decrypt + djb2 hash signature verify
- CMake: requires `-Wl,-z,max-page-size=16384` for Android 16KB page alignment

## Frida Hook Rules (Critical)

These are hard-won lessons from OkHttp3 hook development. **Read before writing any hook script.**

### 1. Never consume one-shot resources in hooks

```
ResponseBody is a one-shot stream — calling body.string()/bytes()/byteStream() consumes it.
If you call these in a hook, the app crashes (IllegalStateException or SIGSEGV).
peekBody() also causes SIGSEGV on some OkHttp versions — do NOT use it.

Correct pattern: hook ResponseBody.string() and intercept the return value when the app calls it.
```

### 2. Request body is safe to read via okio.Buffer — BUT only read ONCE

```
var buffer = Java.use("okio.Buffer").$new();
request.body().writeTo(buffer);   // copies, doesn't consume original
return buffer.readUtf8();
```

**WARNING**: In interceptor chain hooks, `proceed` is called at each layer (8+ times). If each layer calls `readRequestBody`, it can break POST requests. Only read body in the final print function, never in extract/data-collection functions.

### 3. All Java values must be converted to JS primitives immediately with `"" +`

```
Java wrappers are JNI references — they get GC'd ("Wrapper is disposed" error).
NEVER store Java wrappers for later use. Always extract immediately:

  var url = "" + request.url().toString();     // JS string, safe to store
  var method = "" + request.method();           // JS string, safe to store
  var name = "" + it.next();                    // headers iterator
  var value = "" + headers.get(name);           // header value
```

This applies to ALL Java return values: headers keys, headers values, iterator results, toString() results, etc.

### 4. Print BEFORE calling the original method (not after)

```
// ❌ If this.proceed() throws an exception, printInfo never executes
var resp = this.proceed(request);
printInfo(info);

// ✅ Print first — even if proceed() throws, the request is already logged
printInfo(info);
var resp = this.proceed(request);
```

### 5. Use unified tsLog function, never console.log("")

```
console.log("") can silently swallow subsequent output in Frida.
Use a unified logging function with timestamps for all output.
```

### 6. Frida Java Bridge quirks

- **Java method wrappers are not JS Functions**: `.call()`, `.apply()`, `.bind()` do not work. Call directly: `this.method(arg1, arg2)`.
- **String type ambiguity**: Force Java strings to JS strings with `"" + value`, then use `.length` (JS property), not `.length()` (Java method).
- **Closure variable capture**: Always use IIFE in `for` loops when creating hooks — `for` loop `var` is shared across all callbacks.
- **Callback GC**: Use `Java.retain(callback)` or the wrapper gets collected → "Wrapper is disposed" error.
- **`Java.registerClass` names must be unique**: Use a counter suffix.

### 7. Native hooks must be outside `Java.perform()`

`Process`, `Module`, `Interceptor` are Frida global APIs, not Java bridge APIs. Placing them inside `Java.perform()` causes `TypeError: not a function`.

### 8. SO libraries may load lazily

Use a polling pattern: try `Process.findModuleByName()`, if not found, `setInterval` retry every 1s.

### 9. Always enumerate all overloads

OkHttp (especially v4/Kotlin) has many method overloads. Use `method.overloads` array and hook every overload with IIFE — never hook only the default signature.

### 10. Interceptor chain hooks: use header count growth for completeness

OkHttp interceptors modify request at each layer. The outermost `proceed` has incomplete headers.
Track `lastChainHeaderCount[tid]` and only print when header count increases (meaning an interceptor added headers).

## Full Experience Document

See `docs/经验/Frida-Hook开发经验总结.md` for detailed examples, templates, and OkHttp3 safety reference tables.
