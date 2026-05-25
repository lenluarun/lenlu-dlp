import os
import importlib.util
import socket
import sys
import threading
import time
import webbrowser
import json
import logging

# Enable UTF-8 console output and ANSI escape sequences on Windows natively
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

if os.name == 'nt':
    os.system('')

class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Severity status colors (matches website CSS variables)
    GREEN = '\033[38;2;12;189;104m'
    YELLOW = '\033[38;2;255;152;0m'
    RED = '\033[38;2;244;67;54m'
    
    # Theme specific placeholders
    ACCENT = '\033[38;2;0;122;204m'
    TEXT = '\033[38;2;227;227;227m'
    
    @classmethod
    def apply_theme(cls, theme_name: str):
        if theme_name == "ubuntu":
            cls.ACCENT = '\033[38;2;244;116;33m'  # Orange (#f47421)
            cls.TEXT = '\033[38;2;223;219;210m'    # Cream (#dfdbd2)
        elif theme_name == "green":
            cls.ACCENT = '\033[38;2;0;255;102m'    # Classic Green (#00ff66)
            cls.TEXT = '\033[38;2;224;245;231m'   # Mint White (#e0f5e7)
        elif theme_name == "powershell":
            cls.ACCENT = '\033[38;2;238;220;130m'  # Gold (#eedc82)
            cls.TEXT = '\033[38;2;255;255;255m'   # Pure White (#ffffff)
        else:  # dark / default
            cls.ACCENT = '\033[38;2;0;122;204m'    # VS Code Blue (#007acc)
            cls.TEXT = '\033[38;2;227;227;227m'   # Light Gray (#e3e3e3)


# Optional downloader for external binaries
try:
    from scripts.downloader import ensure_binaries
except Exception:
    ensure_binaries = None

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


class ThemeLogFormatter(logging.Formatter):
    _last_checked = 0
    _theme = "dark"

    @classmethod
    def update_theme(cls):
        now = time.time()
        if now - cls._last_checked > 2.0:
            cls._last_checked = now
            try:
                settings = load_settings()
                cls._theme = settings.get("theme", "dark")
                Colors.apply_theme(cls._theme)
            except Exception:
                pass

    def format(self, record: logging.LogRecord) -> str:
        self.update_theme()
        timestamp = f"{Colors.DIM}[{self.formatTime(record, '%H:%M:%S')}]{Colors.RESET} "
        level = record.levelname.lower()
        if level == "info":
            level_tag = f"{Colors.DIM}[info]{Colors.RESET}"
        elif level == "warning":
            level_tag = f"{Colors.YELLOW}{Colors.BOLD}[warning]{Colors.RESET}"
        elif level == "error" or level == "critical":
            level_tag = f"{Colors.RED}{Colors.BOLD}[error]{Colors.RESET}"
        else:
            level_tag = f"{Colors.DIM}[{level}]{Colors.RESET}"
            
        message = record.getMessage()
        message = message.replace("\033[1m", "").replace("\033[0m", "")
        return f"{timestamp}{level_tag} {Colors.TEXT}{message}{Colors.RESET}"


def get_time_prefix() -> str:
    return f"{Colors.DIM}[{time.strftime('%H:%M:%S')}]{Colors.RESET} "


def log_sys(msg):
    ThemeLogFormatter.update_theme()
    print(f"{get_time_prefix()}{Colors.ACCENT}{Colors.BOLD}[system]{Colors.RESET} {Colors.TEXT}{msg}{Colors.RESET}", flush=True)


def log_info(msg):
    ThemeLogFormatter.update_theme()
    print(f"{get_time_prefix()}{Colors.DIM}[info]{Colors.RESET} {Colors.TEXT}{msg}{Colors.RESET}", flush=True)


def log_success(msg):
    ThemeLogFormatter.update_theme()
    print(f"{get_time_prefix()}{Colors.GREEN}{Colors.BOLD}[success]{Colors.RESET} {Colors.TEXT}{msg}{Colors.RESET}", flush=True)


def log_warn(msg):
    ThemeLogFormatter.update_theme()
    print(f"{get_time_prefix()}{Colors.YELLOW}{Colors.BOLD}[warning]{Colors.RESET} {Colors.TEXT}{msg}{Colors.RESET}", flush=True)


def log_error(msg):
    ThemeLogFormatter.update_theme()
    print(f"{get_time_prefix()}{Colors.RED}{Colors.BOLD}[error]{Colors.RESET} {Colors.TEXT}{msg}{Colors.RESET}", flush=True)


try:
    import uvicorn
except ImportError:
    log_error("Required dependency 'uvicorn' is missing.")
    log_info("Install it with: pip install uvicorn fastapi")
    raise SystemExit(1)


backend_spec = importlib.util.spec_from_file_location("lenlu_dlp_gui_runtime", BACKEND_FILE)
if backend_spec is None or backend_spec.loader is None:
    raise SystemExit(f"{Colors.RED}[ERROR] Unable to load backend from {BACKEND_FILE}{Colors.RESET}")
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
            log_sys(f"Server running at {Colors.ACCENT}{BACKEND_URL}{Colors.RESET}. Browser auto-open is disabled by settings.")
            return
        
        url_to_open = settings.get("deployed_frontend_url") or f"{BACKEND_URL}/app"
        log_sys(f"Opening default web browser to: {Colors.ACCENT}{url_to_open}{Colors.RESET}")
        webbrowser.open(url_to_open)
    else:
        log_warn(f"Backend did not become ready at {BACKEND_URL} in time.")


def print_banner(settings: dict):
    theme_name = settings.get("theme", "dark")
    Colors.apply_theme(theme_name)
    
    banner = f"""{Colors.ACCENT}{Colors.BOLD}
██╗     ███████╗███╗   ██╗██╗     ██╗   ██╗    ██████╗ ██╗     ██████╗ 
██║     ██╔════╝████╗  ██║██║     ██║   ██║    ██╔══██╗██║     ██╔══██╗
██║     █████╗  ██╔██╗ ██║██║     ██║   ██║    ██║  ██║██║     ██████╔╝
██║     ██╔══╝  ██║╚██╗██║██║     ██║   ██║    ██║  ██║██║     ██╔═══╝ 
███████╗███████╗██║ ╚████║███████╗╚██████╔╝    ██████╔╝███████╗██║     
╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝ ╚═════╝     ╚═════╝ ╚══════╝╚═╝{Colors.RESET}"""
    print(banner, flush=True)
    
    border = f"{Colors.DIM}----------------------------------------------------------------------{Colors.RESET}"
    print(border, flush=True)
    print(f"               {Colors.BOLD}LENLU DLP // MEDIA TERMINAL v2026.4{Colors.RESET}", flush=True)
    print(border, flush=True)
    
    host_str = f"{BACKEND_HOST}:{BACKEND_PORT}"
    open_browser = "Enabled" if settings.get("open_browser", True) else "Disabled"
    
    theme_display = {
        "ubuntu": "Ubuntu Purple",
        "green": "Classic Green",
        "powershell": "PowerShell Blue",
        "dark": "VS Code Dark"
    }.get(theme_name, theme_name.upper())
    
    print(f"  {Colors.ACCENT}▶{Colors.RESET} {Colors.BOLD}Host Address:{Colors.RESET} {Colors.TEXT}http://{host_str}{Colors.RESET}", flush=True)
    print(f"  {Colors.ACCENT}▶{Colors.RESET} {Colors.BOLD}Active Theme:{Colors.RESET} {Colors.TEXT}{theme_display}{Colors.RESET}", flush=True)
    print(f"  {Colors.ACCENT}▶{Colors.RESET} {Colors.BOLD}Auto-Browser:{Colors.RESET} {Colors.TEXT}{open_browser}{Colors.RESET}", flush=True)
    print(border, flush=True)
    print(flush=True)


# Configure custom loggers
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "theme_formatter": {
            "()": ThemeLogFormatter,
        }
    },
    "handlers": {
        "default": {
            "formatter": "theme_formatter",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "theme_formatter",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}


if __name__ == "__main__":
    settings = load_settings()
    print_banner(settings)
    log_sys("Booting application server...")

    if ensure_binaries:
        try:
            log_info("Checking for helper binaries (yt-dlp, ffmpeg) in ./bin ...")
            found = ensure_binaries()
            if found:
                log_success(f"Binaries ready: {found}")
        except Exception as exc:
            log_warn(f"Binary setup failed (non-fatal): {exc}")
    else:
        log_info("Downloader not available; skipping binary check.")

    if wait_for_port(BACKEND_HOST, BACKEND_PORT, timeout_seconds=1.0):
        if settings.get("open_browser", True):
            url_to_open = settings.get("deployed_frontend_url") or f"{BACKEND_URL}/app"
            log_sys(f"Existing server detected at {BACKEND_URL}; opening browser: {url_to_open}")
            webbrowser.open(url_to_open)
        else:
            log_sys(f"Existing server detected at {BACKEND_URL}.")
        raise SystemExit(0)

    browser_thread = threading.Thread(target=open_browser_when_ready, daemon=True)
    browser_thread.start()

    try:
        uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT, reload=False, log_config=LOG_CONFIG)
    except KeyboardInterrupt:
        print("")
        log_sys("Application server stopped by user interrupt.")
    except Exception as exc:
        print("")
        log_error(f"Server execution terminated: {exc}")
