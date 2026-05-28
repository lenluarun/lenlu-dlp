import asyncio
import json
import logging
import os
import pathlib
import shutil
import socket
import subprocess
import re
from urllib.parse import unquote
import sys
import threading
import time
import webbrowser
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

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
SETTINGS_FILE = os.path.join(GUI_DIR, "settings.json")
STATIC_DIR = CURRENT_DIR


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

try:
    import yt_dlp
except Exception as exc:
    yt_dlp = None
    print(f"[WARNING] yt_dlp import failed: {exc}")


class PrivateNetworkMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            origin = request.headers.get("Origin")
            if origin:
                headers = {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": request.headers.get("Access-Control-Request-Headers", "*"),
                    "Access-Control-Allow-Private-Network": "true",
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Max-Age": "86400",
                }
                return Response(status_code=200, headers=headers)

        response = await call_next(request)
        origin = request.headers.get("Origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response


def get_default_downloads_dir() -> str:
    try:
        downloads = pathlib.Path.home() / "Downloads"
        if downloads.exists():
            return str(downloads)
    except Exception:
        pass
    fallback = os.path.join(CURRENT_DIR, "downloads", "site_downloads")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def load_api_settings() -> Dict[str, Any]:
    settings = {
        "downloads_dir": get_default_downloads_dir(),
        "format_default": "best",
        "sponsorblock": False,
        "embed_metadata": True,
        "embed_thumbnail": True,
        "speed_limit": "none",
        "proxy": "",
        "cookies_file": "",
        "theme": "dark",
        "open_browser": True,
        "deployed_frontend_url": "",
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
                settings.update(saved)
        except Exception:
            pass
    os.makedirs(settings["downloads_dir"], exist_ok=True)
    return settings


def save_api_settings(settings: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=4)


class AppState:
    def __init__(self) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.sse_queues: set = set()
        self.active_thread: Optional[threading.Thread] = None
        self.active_subprocess: Optional[subprocess.Popen] = None
        self.active_task_id: Optional[str] = None
        self.pending_downloads: List[Dict[str, Any]] = []
        self.download_lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.current_download_info = {
            "status": "idle",
            "percent": 0.0,
            "speed_str": "0 B/s",
            "eta_str": "--:--",
            "_size": "0 B / 0 B",
            "filename": "",
            "title": "",
            "type": "api",
        }
        self.log_history: List[Dict[str, str]] = []


state = AppState()
INFO_CACHE: Dict[str, Dict[str, Any]] = {}
INFO_CACHE_TTL_SECONDS = 300


def broadcast_log(message: str, level: str = "info") -> None:
    event = {"type": "log", "level": level, "message": message}
    state.log_history.append(event)
    if len(state.log_history) > 1000:
        state.log_history.pop(0)
    if state.loop and state.sse_queues:
        for queue in list(state.sse_queues):
            state.loop.call_soon_threadsafe(queue.put_nowait, {"event": "log", "data": json.dumps(event)})


def broadcast_progress(progress_data: Dict[str, Any]) -> None:
    state.current_download_info.update(progress_data)
    if state.loop and state.sse_queues:
        for queue in list(state.sse_queues):
            state.loop.call_soon_threadsafe(queue.put_nowait, {"event": "progress", "data": json.dumps(state.current_download_info)})


def _apply_ui_settings_payload(settings: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    if "default_options" in payload and isinstance(payload["default_options"], dict):
        opts = payload["default_options"]
        outtmpl = (opts.get("outtmpl") or "").strip()
        if outtmpl:
            settings["downloads_dir"] = os.path.dirname(outtmpl)
        if opts.get("format"):
            settings["format_default"] = opts.get("format")
        settings["speed_limit"] = opts.get("ratelimit") or "none"
        settings["proxy"] = opts.get("proxy") or ""
        settings["cookies_file"] = opts.get("cookiefile") or ""

    outtmpl_top = (payload.get("outtmpl") or "").strip()
    if outtmpl_top:
        settings["downloads_dir"] = os.path.dirname(outtmpl_top)
    if payload.get("format"):
        settings["format_default"] = payload.get("format")
    if "ratelimit" in payload:
        settings["speed_limit"] = payload.get("ratelimit") or "none"
    if "proxy" in payload:
        settings["proxy"] = payload.get("proxy") or ""
    if "cookiefile" in payload:
        settings["cookies_file"] = payload.get("cookiefile") or ""
    if "theme" in payload:
        settings["theme"] = payload.get("theme") or settings.get("theme", "dark")
    if "open_browser" in payload:
        settings["open_browser"] = bool(payload.get("open_browser"))
    if "deployed_frontend_url" in payload:
        settings["deployed_frontend_url"] = payload.get("deployed_frontend_url") or ""
    return settings


def _to_ui_settings_response(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **settings,
        "default_options": {
            "outtmpl": os.path.join(settings["downloads_dir"], "%(title)s.%(ext)s"),
            "format": settings.get("format_default", "best"),
            "ratelimit": None if settings.get("speed_limit") in [None, "none"] else settings.get("speed_limit"),
            "proxy": settings.get("proxy") or None,
            "cookiefile": settings.get("cookies_file") or None,
            "cookiesfrombrowser": None,
            "sponsorblock_remove": ["sponsor"] if settings.get("sponsorblock") else None,
            "writethumbnail": bool(settings.get("embed_thumbnail", True)),
            "embedmetadata": bool(settings.get("embed_metadata", True)),
            "postprocessors": [{"key": "FFmpegMetadata"}] if settings.get("embed_metadata", True) else [],
        },
    }


def format_url_or_search(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://", "ftp://", "rtmp://", "rtsp://")):
        return f"ytsearch:{value}"
    return value


def _start_download_job(request_payload: Dict[str, Any], settings: Dict[str, Any], task_id: str) -> None:
    url = request_payload["url"]
    format_id = request_payload.get("format_id") or request_payload.get("format") or "best"
    if not url:
        raise HTTPException(status_code=400, detail="Missing video URL or search query.")
    url = format_url_or_search(url)

    def worker() -> None:
        state.cancel_event.clear()
        state.active_task_id = task_id
        outtmpl = os.path.join(settings["downloads_dir"], "%(title)s.%(ext)s")
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--newline",
            "--no-playlist",
            "--concurrent-fragments",
            "4",
            "-f",
            str(format_id),
            "-o",
            outtmpl,
            url,
        ]
        ratelimit = request_payload.get("ratelimit")
        if ratelimit and ratelimit != "none":
            cmd.extend(["--limit-rate", str(ratelimit)])
        if settings.get("proxy"):
            cmd.extend(["--proxy", settings["proxy"]])
        if settings.get("cookies_file") and os.path.exists(settings["cookies_file"]):
            cmd.extend(["--cookies", settings["cookies_file"]])

        progress_rx = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+(.+?)\s+at\s+(.+?)\s+ETA\s+(.+)$")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            state.active_subprocess = proc
            current_title = "Downloading..."
            if proc.stdout:
                for raw_line in proc.stdout:
                    if state.cancel_event.is_set() and proc.poll() is None:
                        proc.terminate()
                        break
                    line = (raw_line or "").strip()
                    if not line:
                        continue
                    if "Destination:" in line:
                        current_title = os.path.basename(line.split("Destination:", 1)[1].strip())
                    if "[download]" in line:
                        m = progress_rx.search(line)
                        if m:
                            pct, total, speed, eta = m.groups()
                            broadcast_progress(
                                {
                                    "status": "downloading",
                                    "percent": float(pct),
                                    "speed_str": speed.strip(),
                                    "eta_str": eta.strip(),
                                    "_size": total.strip(),
                                    "title": current_title,
                                    "filename": current_title,
                                }
                            )
                    broadcast_log(line, "info")
            rc = proc.wait(timeout=10)
            if rc != 0 and not state.cancel_event.is_set():
                raise RuntimeError(f"yt-dlp exited with code {rc}")
            broadcast_log("[system] Download completed successfully!", "info")
            broadcast_progress({"status": "success", "percent": 100.0, "eta_str": "00:00"})
        except Exception as exc:
            broadcast_log(f"[error] Download failed: {exc}", "error")
            if state.cancel_event.is_set():
                broadcast_progress({"status": "cancelled", "percent": 0.0, "title": "Cancelled"})
            else:
                broadcast_progress({"status": "error", "percent": 0.0})
        finally:
            state.active_subprocess = None
            state.active_thread = None
            state.active_task_id = None
            with state.download_lock:
                if state.pending_downloads:
                    next_job = state.pending_downloads.pop(0)
                    _start_download_job(next_job["payload"], next_job["settings"], next_job["task_id"])

    state.active_thread = threading.Thread(target=worker, daemon=True)
    state.active_thread.start()


def _get_info_impl(url: str) -> Dict[str, Any]:
    if yt_dlp is None:
        raise HTTPException(status_code=500, detail="yt-dlp is not installed.")
    url = format_url_or_search(url)
    if not url:
        raise HTTPException(status_code=400, detail="Empty URL or search query.")
    settings = load_api_settings()
    cached = INFO_CACHE.get(url)
    now_ts = time.time()
    if cached and (now_ts - cached.get("ts", 0) <= INFO_CACHE_TTL_SECONDS):
        return cached["data"]
    ydl_opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    if settings.get("proxy"):
        ydl_opts["proxy"] = settings["proxy"]
    if settings.get("cookies_file") and os.path.exists(settings["cookies_file"]):
        ydl_opts["cookiefile"] = settings["cookies_file"]
    try:
        # Fetch metadata through a direct terminal command for faster, CLI-native behavior.
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-single-json",
            "--no-playlist",
            "--skip-download",
            "--no-warnings",
            "--no-call-home",
            "--socket-timeout",
            "10",
            "--extractor-retries",
            "1",
            "--retries",
            "1",
            "--playlist-end",
            "1",
            "--extractor-args",
            "youtube:player_client=android",
            url,
        ]
        if settings.get("proxy"):
            cmd.extend(["--proxy", settings["proxy"]])
        if settings.get("cookies_file") and os.path.exists(settings["cookies_file"]):
            cmd.extend(["--cookies", settings["cookies_file"]])

        result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise HTTPException(status_code=400, detail=(result.stderr or result.stdout or "yt-dlp metadata fetch failed.").strip())
        info = json.loads(result.stdout or "{}")
        raw_formats = info.get("formats") or []
        formats_list = []
        for item in raw_formats:
            acodec = item.get("acodec", "none")
            vcodec = item.get("vcodec", "none")
            stream_type = "video"
            if acodec != "none" and vcodec == "none":
                stream_type = "audio"
            elif acodec == "none" and vcodec == "none":
                continue
            filesize = item.get("filesize") or item.get("filesize_approx")
            filesize_mb = f"{round(filesize / (1024 * 1024), 1)} MB" if filesize else "unknown"
            resolution = item.get("resolution") or item.get("format_note") or "unknown"
            if stream_type == "audio":
                resolution = f"audio ({item.get('abr', 128)} kbps)"
            formats_list.append(
                {
                    "format_id": item.get("format_id"),
                    "ext": item.get("ext"),
                    "resolution": resolution,
                    "vcodec": vcodec,
                    "acodec": acodec,
                    "filesize": filesize_mb,
                    "fps": item.get("fps", ""),
                    "type": stream_type,
                    "tbr": round(item.get("tbr") or 0, 1),
                }
            )
        # Keep UI responsive: cap to top candidates rather than returning very large format arrays.
        formats_list.sort(key=lambda x: (x.get("tbr") or 0), reverse=True)
        formats_list = formats_list[:80]

        response_data = {
            "title": info.get("title", "Unknown Title"),
            "duration": info.get("duration") or 0,
            "thumbnail": info.get("thumbnail", ""),
            "channel": info.get("channel", "Unknown Channel"),
            "description": (info.get("description", "")[:500] + "...") if info.get("description") else "",
            "formats": formats_list,
        }
        INFO_CACHE[url] = {"ts": now_ts, "data": response_data}
        if len(INFO_CACHE) > 200:
            oldest_key = min(INFO_CACHE.keys(), key=lambda k: INFO_CACHE[k].get("ts", 0))
            INFO_CACHE.pop(oldest_key, None)
        return response_data
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


app = FastAPI(title="LENLU DLP API")
app.add_middleware(PrivateNetworkMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    state.loop = asyncio.get_running_loop()
    settings = load_api_settings()
    try:
        app.mount("/api/media", StaticFiles(directory=settings["downloads_dir"]), name="media")
    except Exception:
        pass


@app.get("/api/settings")
def get_settings_endpoint() -> Dict[str, Any]:
    return _to_ui_settings_response(load_api_settings())


@app.post("/api/settings")
def save_settings_endpoint(new_settings: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_api_settings()
    settings = _apply_ui_settings_payload(settings, new_settings or {})
    save_api_settings(settings)
    try:
        app.mount("/api/media", StaticFiles(directory=settings["downloads_dir"]), name="media")
    except Exception:
        pass
    return _to_ui_settings_response(settings)


@app.post("/api/info")
def post_info(payload: Dict[str, Any]):
    return _get_info_impl((payload or {}).get("url", ""))


@app.post("/api/download")
def trigger_download(request: Request, payload: Optional[Dict[str, Any]] = None):
    if yt_dlp is None:
        raise HTTPException(status_code=500, detail="yt-dlp is not installed.")
    request_payload = dict(payload or {})
    query_params = dict(request.query_params)
    request_payload.update({k: v for k, v in query_params.items() if v is not None})
    settings = load_api_settings()

    task_id = str(int(time.time() * 1000))
    with state.download_lock:
        if state.active_thread is None:
            _start_download_job(request_payload, settings, task_id)
            return {"status": "started", "task_id": task_id}
        state.pending_downloads.append({"payload": request_payload, "settings": settings, "task_id": task_id})
        return {"status": "queued", "task_id": task_id, "queue_position": len(state.pending_downloads)}


@app.post("/api/cancel")
def cancel_task():
    state.cancel_event.set()
    proc = state.active_subprocess
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    return {"status": "cancelling", "message": "Cancellation request transmitted."}


@app.get("/api/task-status")
def get_task_status():
    return {
        "running": state.active_thread is not None,
        "task_id": state.active_task_id,
        "pending_count": len(state.pending_downloads),
        "status": state.current_download_info.get("status", "idle"),
        "title": state.current_download_info.get("title", ""),
        "percent": state.current_download_info.get("percent", 0.0),
    }


@app.get("/api/library")
def get_library():
    settings = load_api_settings()
    downloads_dir = settings["downloads_dir"]
    files = []
    if os.path.exists(downloads_dir):
        for entry in os.scandir(downloads_dir):
            if not entry.is_file():
                continue
            ext = pathlib.Path(entry.name).suffix.lower()
            if ext in [".part", ".ytdl", ".temp"]:
                continue
            stat = entry.stat()
            files.append({"name": entry.name, "size": stat.st_size, "modified": stat.st_mtime})
    files.sort(key=lambda item: item["modified"], reverse=True)
    return {"folder": downloads_dir, "files": files}


@app.delete("/api/library/{filename}")
def delete_library_file(filename: str):
    settings = load_api_settings()
    # Accept URL-encoded names from frontend paths and block traversal.
    decoded_name = unquote(filename or "")
    safe_name = os.path.basename(decoded_name)
    if not safe_name or safe_name != decoded_name:
        raise HTTPException(status_code=400, detail="Invalid file path")
    filepath = os.path.join(settings["downloads_dir"], safe_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    last_exc: Optional[Exception] = None
    for _ in range(4):
        try:
            os.chmod(filepath, 0o666)
        except Exception:
            pass
        try:
            os.remove(filepath)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            time.sleep(0.25)
    if last_exc is not None:
        raise HTTPException(status_code=500, detail=f"Delete failed: {last_exc}")
    return {"status": "deleted", "name": safe_name}


@app.post("/api/library/clear_all")
def clear_library():
    settings = load_api_settings()
    downloads_dir = settings["downloads_dir"]
    removed = 0
    if os.path.exists(downloads_dir):
        for entry in os.scandir(downloads_dir):
            path = entry.path
            try:
                if entry.is_file() or entry.is_symlink():
                    os.remove(path)
                    removed += 1
                elif entry.is_dir():
                    shutil.rmtree(path)
                    removed += 1
            except Exception:
                continue
    return {"status": "ok", "removed": removed}


@app.get("/api/play/{filename}")
def play_downloaded_file(filename: str):
    settings = load_api_settings()
    safe_name = os.path.basename(filename)
    filepath = os.path.join(settings["downloads_dir"], safe_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath)


@app.get("/api/progress/stream")
async def progress_stream(request: Request):
    async def event_generator():
        queue = asyncio.Queue()
        state.sse_queues.add(queue)
        for log in state.log_history:
            yield f"event: log\ndata: {json.dumps(log)}\n\n"
        yield f"event: progress\ndata: {json.dumps(state.current_download_info)}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: {message['event']}\ndata: {message['data']}\n\n"
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            state.sse_queues.discard(queue)
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/execute")
@app.post("/api/shell")
async def trigger_shell_command(payload: Dict[str, Any]):
    command = (payload.get("command") or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="Empty command string.")
    return {"status": "started", "message": f"Command accepted: {command}"}


@app.post("/api/select-download-folder")
def select_download_folder() -> Dict[str, Any]:
    settings = load_api_settings()
    initial_dir = settings.get("downloads_dir") or get_default_downloads_dir()
    try:
        from tkinter import Tk, filedialog
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Folder picker is unavailable: {exc}")
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(initialdir=initial_dir, title="Select LENLU DLP download folder")
    finally:
        root.destroy()
    if not selected:
        raise HTTPException(status_code=400, detail="Folder selection cancelled.")
    settings["downloads_dir"] = selected
    save_api_settings(settings)
    return {"status": "ok", "path": selected}


@app.get("/")
def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return "LENLU DLP Web GUI Static folder initialized. Please create index.html inside the root folder."


@app.get("/app")
@app.get("/local_host.html")
def get_app():
    app_path = os.path.join(STATIC_DIR, "local_host.html")
    if os.path.exists(app_path):
        return FileResponse(app_path)
    raise HTTPException(status_code=404, detail="local_host.html not found")


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
