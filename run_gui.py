import os
import importlib.util
import socket
import sys
import threading
import time
import webbrowser
import json

# Optional downloader for external binaries
try:
    from scripts.downloader import ensure_binaries
except Exception:
    ensure_binaries = None

try:
    import uvicorn
except ImportError:
    print("[ERROR] Required dependency 'uvicorn' is missing.")
    print("Install it with: pip install uvicorn fastapi")
    raise SystemExit(1)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
GUI_DIR = os.path.join(CURRENT_DIR, "lenlu_dlp_gui")
BACKEND_FILE = os.path.join(GUI_DIR, "gui_backend.py")
SETTINGS_FILE = os.path.join(GUI_DIR, "settings.json")


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

backend_spec = importlib.util.spec_from_file_location("lenlu_dlp_gui_runtime", BACKEND_FILE)
if backend_spec is None or backend_spec.loader is None:
    raise SystemExit(f"Unable to load backend from {BACKEND_FILE}")
backend_module = importlib.util.module_from_spec(backend_spec)
backend_spec.loader.exec_module(backend_module)
app = backend_module.app


def wait_for_port(host: str, port: int, timeout_seconds: float = 30.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


def open_browser_when_ready() -> None:
    if wait_for_port(BACKEND_HOST, BACKEND_PORT, timeout_seconds=45.0):
        settings = load_settings()
        if not settings.get("open_browser", True):
            print(f"[SYSTEM] Server running at {BACKEND_URL}. Browser auto-open is disabled by settings.")
            return
        
        url_to_open = settings.get("deployed_frontend_url") or BACKEND_URL
        print(f"[SYSTEM] Opening default web browser to: {url_to_open}")
        webbrowser.open(url_to_open)
    else:
        print(f"[WARNING] Backend did not become ready at {BACKEND_URL} in time.")


if __name__ == "__main__":
    print("==================================================================")
    print("                 LENLU DLP - RETRO TERMINAL Web GUI                ")
    print("==================================================================")
    print("[SYSTEM] Booting application server...")

    if ensure_binaries:
        try:
            print("[SYSTEM] Checking for helper binaries (yt-dlp, ffmpeg) in ./bin ...")
            found = ensure_binaries()
            if found:
                print(f"[SYSTEM] Binaries ready: {found}")
        except Exception as exc:
            print(f"[SYSTEM] Binary setup failed (non-fatal): {exc}")
    else:
        print("[SYSTEM] Downloader not available; skipping binary check.")

    if wait_for_port(BACKEND_HOST, BACKEND_PORT, timeout_seconds=1.0):
        settings = load_settings()
        if settings.get("open_browser", True):
            url_to_open = settings.get("deployed_frontend_url") or BACKEND_URL
            print(f"[SYSTEM] Existing server detected at {BACKEND_URL}; opening browser: {url_to_open}")
            webbrowser.open(url_to_open)
        else:
            print(f"[SYSTEM] Existing server detected at {BACKEND_URL}.")
        raise SystemExit(0)

    browser_thread = threading.Thread(target=open_browser_when_ready, daemon=True)
    browser_thread.start()

    try:
        uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT, reload=False)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Application server stopped by user interrupt.")
    except Exception as exc:
        print(f"\n[ERROR] Server execution terminated: {exc}")
