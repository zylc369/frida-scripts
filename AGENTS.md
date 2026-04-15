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

⚠️ You **MUST** read the relevant knowledge base docs below before writing any hook script. These are hard-won lessons from OkHttp3 hook development.

### Mandatory (always read first)
- `docs/经验/01-核心原则.md` — 4 core principles + checklist. Read before ANY hook work.

### Load on demand based on task
| Task | Required Reading |
|------|-----------------|
| Writing Java hook scripts | `docs/经验/02-Hook架构与模板.md` + `docs/经验/03-Java-Bridge陷阱.md` |
| Writing Native hook scripts | `docs/经验/04-Native-Hook要点.md` |
| Hooking OkHttp3 | `docs/经验/06-OkHttp3安全方法参考.md` |
| Debugging hook issues | `docs/经验/05-调试策略.md` |

> Full index: `docs/经验/Frida-Hook开发经验总结.md`
