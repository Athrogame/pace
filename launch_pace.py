"""Pace desktop launcher (Windows, macOS, Linux).

Double-click the "Pace" shortcut (or run `pythonw launch_pace.py`) and Pace opens in its own
app window, with no tabs or address bar. The launcher:
  1. starts Pace's server in the background, unless one is already running on the port;
  2. opens Edge or Chrome in app mode, with its own profile so it runs as a separate app;
  3. stops the server when you close the window (only if this launcher started it).

Logs go to <your app-data folder>/Pace/launcher.log.
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PACE_PORT", "8000"))   # 8000 is the origin Google sign-in allows
URL = f"http://localhost:{PORT}/#/today"
DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "Pace"
LOG = DATA / "launcher.log"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg: str) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %I:%M:%S %p ") + msg + "\n")


def server_up() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/safety", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def start_server():
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":   # the server itself can run without a console too
        python = python.with_name("pythonw.exe")
    out = LOG.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [str(python), "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=HERE, stdout=out, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
        env={k: v for k, v in os.environ.items() if k != "PACE_NOW"},   # real clock, not the demo's
    )
    for _ in range(80):   # up to ~20 seconds
        if server_up():
            return proc
        if proc.poll() is not None:
            raise RuntimeError("Pace's server stopped while starting. See " + str(LOG))
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("Pace's server didn't start in time. See " + str(LOG))


def find_browser():
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def pace_window_open(browser_pid: int) -> bool:
    """Windows only: is there a visible window titled "Pace" owned by our browser process?"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def check(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == browser_pid:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value.startswith("Pace"):
                    found.append(hwnd)
                    return False
        return True

    user32.EnumWindows(check, 0)
    return bool(found)


def wait_for_window(window) -> None:
    """Return when the Pace window closes. Edge can leave other windows (or a background process)
    alive in the app's profile, so on Windows we watch the Pace window itself, then close the rest."""
    if os.name != "nt":
        window.wait()
        return
    seen, missing, waited = False, 0, 0
    while window.poll() is None:
        if pace_window_open(window.pid):
            seen, missing = True, 0
        elif seen:
            missing += 1
            if missing >= 2:   # gone for 2 checks in a row: the person closed it
                break
        elif waited > 120:     # never found a "Pace" window: fall back to the process
            window.wait()
            return
        time.sleep(1)
        waited += 1
    if window.poll() is None:
        subprocess.run(["taskkill", "/PID", str(window.pid), "/T", "/F"],
                       creationflags=NO_WINDOW, capture_output=True)


def show_error(message: str) -> None:
    log("ERROR " + message)
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Pace", 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> None:
    browser = find_browser()
    if not browser:
        show_error("Pace needs Microsoft Edge or Google Chrome to open its window.")
        return
    started = None
    try:
        if not server_up():
            log("starting server")
            started = start_server()
        log("opening window")
        window = subprocess.Popen([
            browser, f"--app={URL}", f"--user-data-dir={DATA / 'window-profile'}",
            "--window-size=1100,860", "--no-first-run", "--no-default-browser-check",
        ])
        wait_for_window(window)
        log("window closed")
    except Exception as e:
        show_error(str(e))
    finally:
        if started and started.poll() is None:
            started.terminate()
            log("server stopped")


if __name__ == "__main__":
    main()
