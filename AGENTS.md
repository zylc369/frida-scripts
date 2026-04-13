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

### 2. Request body is safe to read via okio.Buffer

```
var buffer = Java.use("okio.Buffer").$new();
request.body().writeTo(buffer);   // copies, doesn't consume original
return buffer.readUtf8();
```

### 3. Frida Java Bridge quirks

- **Java method wrappers are not JS Functions**: `.call()`, `.apply()`, `.bind()` do not work. Call directly: `this.method(arg1, arg2)`.
- **String type ambiguity**: Force Java strings to JS strings with `"" + value`, then use `.length` (JS property), not `.length()` (Java method).
- **Closure variable capture**: Always use IIFE in `for` loops when creating hooks — `for` loop `var` is shared across all callbacks.
- **Callback GC**: Use `Java.retain(callback)` or the wrapper gets collected → "Wrapper is disposed" error.
- **`Java.registerClass` names must be unique**: Use a counter suffix.

### 4. Native hooks must be outside `Java.perform()`

`Process`, `Module`, `Interceptor` are Frida global APIs, not Java bridge APIs. Placing them inside `Java.perform()` causes `TypeError: not a function`.

### 5. SO libraries may load lazily

Use a polling pattern: try `Process.findModuleByName()`, if not found, `setInterval` retry every 1s.

### 6. Always enumerate all overloads

OkHttp (especially v4/Kotlin) has many method overloads. Use `method.overloads` array and hook every overload with IIFE — never hook only the default signature.

## Full Experience Document

See `docs/经验/Frida-Hook开发经验总结.md` for detailed examples, templates, and OkHttp3 safety reference tables.
