import asyncio
import json
import logging
import os
import pathlib
import shutil
import socket
import subprocess
import re
import signal
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

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    tk = None
    filedialog = None

def __handle_exit(sig, frame):
    try:
        if 'state' in globals() and state.active_subprocess:
            state.active_subprocess.terminate()
    except Exception:
        pass
    sys.exit(0)

if os.name != 'nt': # Unix
    signal.signal(signal.SIGTERM, __handle_exit)
    signal.signal(signal.SIGINT, __handle_exit)
else: # Windows
    try:
        signal.signal(signal.SIGINT, __handle_exit)
    except Exception:
        pass

if getattr(sys, 'frozen', False):
    # When bundled by PyInstaller, the files are extracted to a temporary folder (_MEIPASS)
    BUNDLE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    PROJECT_ROOT = BUNDLE_DIR
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LENLU DLP")
else:
    # If running as a script, use the script's directory
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(BUNDLE_DIR))
    CONFIG_DIR = os.path.join(PROJECT_ROOT, "app", "gui")

class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    GREEN = '\033[38;2;12;189;104m'
    YELLOW = '\033[38;2;255;152;0m'
    RED = '\033[38;2;244;67;54m'
    ACCENT = '\033[38;2;0;122;204m'
    TEXT = '\033[38;2;227;227;227m'

    @classmethod
    def apply_theme(cls, theme_name: str):
        if theme_name == "ubuntu":
            cls.ACCENT = '\033[38;2;244;116;33m'
            cls.TEXT = '\033[38;2;223;219;210m'
        elif theme_name == "green":
            cls.ACCENT = '\033[38;2;0;255;102m'
            cls.TEXT = '\033[38;2;224;245;231m'
        elif theme_name == "powershell":
            cls.ACCENT = '\033[38;2;238;220;130m'
            cls.TEXT = '\033[38;2;255;255;255m'
        else:
            cls.ACCENT = '\033[38;2;0;122;204m'
            cls.TEXT = '\033[38;2;227;227;227m'

try:
    from scripts.downloader import ensure_binaries
except Exception:
    ensure_binaries = None

CURRENT_DIR = BUNDLE_DIR
APP_VERSION = "3.1.0"
UPDATE_URL = "https://github.com/lenluarun/lenlu-dlp/releases/latest"
BACKEND_HOST = "0.0.0.0"
BACKEND_PORT = 8000
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
GUI_DIR = os.path.join(PROJECT_ROOT, "app", "gui")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
STATIC_DIR = PROJECT_ROOT
os.makedirs(CONFIG_DIR, exist_ok=True)

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
    raise SystemExit(1)

try:
    import yt_dlp
except Exception as exc:
    yt_dlp = None
    log_error(f"CRITICAL: yt_dlp import failed: {exc}")

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

_original_popen = subprocess.Popen
def _tracked_popen(*args, **kwargs):
    proc = _original_popen(*args, **kwargs)
    state.active_subprocess = proc
    return proc
subprocess.Popen = _tracked_popen

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
    ratelimit = request_payload.get("ratelimit") or "none"

    def worker() -> None:
        state.cancel_event.clear()
        state.active_task_id = task_id
        outtmpl = os.path.join(settings["downloads_dir"], "%(title)s.%(ext)s")

        # FIX: format_id was missing from the scope, using format_id from the outer function
        format_str = format_id

        ydl_opts = {
            "outtmpl": outtmpl,
            "format": format_str,
            "newline": True,
            "noplaylist": True,
            "concurrent_fragments": 4,
        }

        if format_str in ("mp3-320", "mp3-256", "mp3-192", "mp3-128", "mp3", "flac", "wav", "m4a", "opus"):
            audio_type = "mp3" if format_str.startswith("mp3") else format_str
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_type,
                "preferredquality": "320" if "320" in format_str else ("256" if "256" in format_str else ("192" if "192" in format_str else "128")),
            }]
            ydl_opts["format"] = "bestaudio/best"
        elif "+" in format_str or format_str.startswith("bestvideo"):
            ydl_opts["merge_output_format"] = "mp4"

        if ratelimit and ratelimit != "none":
            ydl_opts["ratelimit"] = int(ratelimit) * 1024 # Convert KB/s to B/s
        if settings.get("proxy"):
            ydl_opts["proxy"] = settings["proxy"]
        if settings.get("cookies_file") and os.path.exists(settings["cookies_file"]):
            ydl_opts["cookiefile"] = settings["cookies_file"]

        def progress_hook(d):
            if state.cancel_event.is_set():
                cancel_cls = getattr(yt_dlp.utils, "DownloadCancelled", Exception) if yt_dlp else Exception
                raise cancel_cls("Download terminated by user.")
            if d.get("status") == "downloading":
                pct_str = d.get("_percent_str", "0").replace("%", "").strip()
                try:
                    pct = float(pct_str)
                except Exception:
                    pct = 0.0
                speed = d.get("_speed_str", "0 B/s")
                eta = d.get("_eta_str", "--:--")
                total = d.get("_total_bytes_str", "0 B")

                broadcast_progress({
                    "status": "downloading",
                    "percent": pct,
                    "speed_str": speed,
                    "eta_str": eta,
                    "_size": total,
                    "title": os.path.basename(d.get("filename", "")),
                    "filename": os.path.basename(d.get("filename", "")),
                })
            elif d.get("status") == "finished":
                broadcast_log(f"Finished downloading {d.get('filename')}", "info")

        def postprocessor_hook(d):
            if state.cancel_event.is_set():
                cancel_cls = getattr(yt_dlp.utils, "DownloadCancelled", Exception) if yt_dlp else Exception
                raise cancel_cls("Post-processing terminated by user.")

        ydl_opts["progress_hooks"] = [progress_hook]
        ydl_opts["postprocessor_hooks"] = [postprocessor_hook]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if state.cancel_event.is_set():
                broadcast_log("[system] Download process terminated by user.", "warning")
                broadcast_progress({"status": "cancelled", "percent": 0.0, "title": "Cancelled"})
            else:
                broadcast_log("[system] Download completed successfully!", "info")
                broadcast_progress({"status": "success", "percent": 100.0, "eta_str": "00:00"})
        except Exception as exc:
            if state.cancel_event.is_set():
                broadcast_log("[system] Download was terminated by user.", "warning")
                broadcast_progress({"status": "cancelled", "percent": 0.0, "title": "Cancelled"})
            else:
                broadcast_log(f"[error] Download failed: {exc}", "error")
                broadcast_progress({"status": "error", "percent": 0.0, "message": str(exc)})
        finally:
            state.active_subprocess = None
            state.active_thread = None
            state.active_task_id = None
            if not state.cancel_event.is_set():
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
        ydl_opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
        if settings.get("proxy"):
            ydl_opts["proxy"] = settings["proxy"]
        if settings.get("cookies_file") and os.path.exists(settings["cookies_file"]):
            ydl_opts["cookiefile"] = settings["cookies_file"]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        raw_formats = info.get("formats") or []
        if not raw_formats and info.get("entries"):
            first_entry = (info.get("entries") or [{}])[0] or {}
            raw_formats = first_entry.get("formats") or []
            if not info.get("title") or info.get("title") == url:
                info["title"] = first_entry.get("title") or info.get("title")
            if not info.get("thumbnail"):
                info["thumbnail"] = first_entry.get("thumbnail") or ""
            if not info.get("duration"):
                info["duration"] = first_entry.get("duration") or 0

        formats_list = []
        for item in raw_formats:
            acodec = str(item.get("acodec") or "none")
            vcodec = str(item.get("vcodec") or "none")
            ext = str(item.get("ext") or "mp4")
            format_note = str(item.get("format_note") or "")
            if ext == "mhtml" or "storyboard" in format_note.lower():
                continue
            stream_type = "video"
            if acodec != "none" and vcodec == "none":
                stream_type = "audio"
            elif acodec != "none" and vcodec != "none":
                stream_type = "combined"
            elif acodec == "none" and vcodec == "none":
                if item.get("height") or item.get("resolution") or item.get("fps"):
                    stream_type = "video"
                elif item.get("abr") or item.get("asr"):
                    stream_type = "audio"
                else:
                    continue
            filesize = item.get("filesize")
            filesize_approx = item.get("filesize_approx")
            res_val = item.get("resolution")
            if not res_val or res_val == "unknown":
                if item.get("height"):
                    res_val = f"{item.get('width', '')}x{item.get('height')}" if item.get('width') else f"{item.get('height')}p"
                elif stream_type == "audio":
                    abr = round(item.get("abr") or item.get("tbr") or 128)
                    res_val = f"audio ({abr} kbps)"
                else:
                    res_val = format_note or "standard"
            formats_list.append(
                {
                    "format_id": str(item.get("format_id") or ""),
                    "ext": ext,
                    "resolution": res_val,
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "vcodec": vcodec,
                    "acodec": acodec,
                    "filesize": filesize,
                    "filesize_approx": filesize_approx,
                    "fps": item.get("fps") or "",
                    "type": stream_type,
                    "tbr": round(item.get("tbr") or 0, 1) if item.get("tbr") else None,
                    "abr": round(item.get("abr") or 0, 1) if item.get("abr") else None,
                    "vbr": round(item.get("vbr") or 0, 1) if item.get("vbr") else None,
                    "asr": item.get("asr"),
                    "audio_channels": item.get("audio_channels"),
                    "dynamic_range": item.get("dynamic_range"),
                    "container": item.get("container") or ext,
                    "protocol": item.get("protocol"),
                    "format_note": format_note,
                }
            )

        has_video = any(f.get("type") in ("video", "combined") for f in formats_list)
        has_audio = any(f.get("type") in ("audio", "combined") for f in formats_list)
        synth_presets = []
        if has_video and has_audio:
            synth_presets.extend([
                {
                    "format_id": "bestvideo+bestaudio/best",
                    "ext": "mp4",
                    "resolution": "Auto Max Quality",
                    "height": 2160,
                    "width": 3840,
                    "vcodec": "Best Video (DASH)",
                    "acodec": "Best Audio (DASH)",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": 60,
                    "type": "combined",
                    "tbr": 25000,
                    "abr": None,
                    "vbr": None,
                    "asr": 48000,
                    "audio_channels": 2,
                    "dynamic_range": "HDR/SDR",
                    "container": "mp4",
                    "protocol": "https",
                    "format_note": "Highest quality video merged with best audio track (Auto)",
                },
                {
                    "format_id": "bestvideo[height<=2160]+bestaudio/best",
                    "ext": "mp4",
                    "resolution": "3840x2160 (4K UHD)",
                    "height": 2160,
                    "width": 3840,
                    "vcodec": "AV1 / VP9",
                    "acodec": "Opus / AAC",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": 60,
                    "type": "combined",
                    "tbr": 18500,
                    "abr": None,
                    "vbr": None,
                    "asr": 48000,
                    "audio_channels": 2,
                    "dynamic_range": "HDR",
                    "container": "mp4",
                    "protocol": "https",
                    "format_note": "4K Ultra HD Pre-merged Combined MP4",
                },
                {
                    "format_id": "bestvideo[height<=1440]+bestaudio/best",
                    "ext": "mp4",
                    "resolution": "2560x1440 (1440p QHD)",
                    "height": 1440,
                    "width": 2560,
                    "vcodec": "AV1 / VP9",
                    "acodec": "Opus / AAC",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": 60,
                    "type": "combined",
                    "tbr": 10500,
                    "abr": None,
                    "vbr": None,
                    "asr": 48000,
                    "audio_channels": 2,
                    "dynamic_range": "SDR",
                    "container": "mp4",
                    "protocol": "https",
                    "format_note": "1440p Quad HD Pre-merged Combined MP4",
                },
                {
                    "format_id": "bestvideo[height<=1080]+bestaudio/best",
                    "ext": "mp4",
                    "resolution": "1920x1080 (1080p FHD)",
                    "height": 1080,
                    "width": 1920,
                    "vcodec": "H.264 / AV1",
                    "acodec": "AAC / Opus",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": 60,
                    "type": "combined",
                    "tbr": 5800,
                    "abr": None,
                    "vbr": None,
                    "asr": 48000,
                    "audio_channels": 2,
                    "dynamic_range": "SDR",
                    "container": "mp4",
                    "protocol": "https",
                    "format_note": "1080p Full HD Pre-merged Combined MP4",
                },
                {
                    "format_id": "bestvideo[height<=720]+bestaudio/best",
                    "ext": "mp4",
                    "resolution": "1280x720 (720p HD)",
                    "height": 720,
                    "width": 1280,
                    "vcodec": "H.264 / AV1",
                    "acodec": "AAC / Opus",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": 60,
                    "type": "combined",
                    "tbr": 3200,
                    "abr": None,
                    "vbr": None,
                    "asr": 48000,
                    "audio_channels": 2,
                    "dynamic_range": "SDR",
                    "container": "mp4",
                    "protocol": "https",
                    "format_note": "720p HD Pre-merged Combined MP4",
                },
            ])
        if has_audio:
            synth_presets.extend([
                {
                    "format_id": "mp3-320",
                    "ext": "mp3",
                    "resolution": "audio (320 kbps)",
                    "height": None,
                    "width": None,
                    "vcodec": "none",
                    "acodec": "mp3 (LAME CBR)",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": "",
                    "type": "audio",
                    "tbr": 320,
                    "abr": 320,
                    "vbr": None,
                    "asr": 48000,
                    "audio_channels": 2,
                    "dynamic_range": "—",
                    "container": "mp3",
                    "protocol": "https",
                    "format_note": "Master 320kbps CBR MP3 Audio Extraction",
                },
                {
                    "format_id": "flac",
                    "ext": "flac",
                    "resolution": "audio (Lossless)",
                    "height": None,
                    "width": None,
                    "vcodec": "none",
                    "acodec": "flac",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": "",
                    "type": "audio",
                    "tbr": 950,
                    "abr": 950,
                    "vbr": None,
                    "asr": 48000,
                    "audio_channels": 2,
                    "dynamic_range": "—",
                    "container": "flac",
                    "protocol": "https",
                    "format_note": "Audiophile 24-bit Lossless FLAC Audio",
                },
                {
                    "format_id": "wav",
                    "ext": "wav",
                    "resolution": "audio (1411 kbps PCM)",
                    "height": None,
                    "width": None,
                    "vcodec": "none",
                    "acodec": "pcm_s16le",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": "",
                    "type": "audio",
                    "tbr": 1411,
                    "abr": 1411,
                    "vbr": None,
                    "asr": 48000,
                    "audio_channels": 2,
                    "dynamic_range": "—",
                    "container": "wav",
                    "protocol": "https",
                    "format_note": "Studio Uncompressed PCM WAV Audio",
                },
                {
                    "format_id": "m4a",
                    "ext": "m4a",
                    "resolution": "audio (256 kbps)",
                    "height": None,
                    "width": None,
                    "vcodec": "none",
                    "acodec": "mp4a.40.2 (AAC-LC)",
                    "filesize": None,
                    "filesize_approx": None,
                    "fps": "",
                    "type": "audio",
                    "tbr": 256,
                    "abr": 256,
                    "vbr": None,
                    "asr": 44100,
                    "audio_channels": 2,
                    "dynamic_range": "—",
                    "container": "m4a",
                    "protocol": "https",
                    "format_note": "Apple Native 256kbps AAC M4A",
                },
            ])
        formats_list.sort(key=lambda x: (
            1 if x.get("type") == "combined" else (2 if x.get("type") == "video" else 3),
            -(x.get("height") or 0),
            -(x.get("tbr") or x.get("abr") or 0)
        ))
        all_final_formats = synth_presets + formats_list
        response_data = {
            "title": info.get("title", "Unknown Title"),
            "duration": info.get("duration") or 0,
            "thumbnail": info.get("thumbnail", ""),
            "channel": info.get("channel", "Unknown Channel"),
            "description": (info.get("description", "")[:500] + "...") if info.get("description") else "",
            "formats": all_final_formats,
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

@app.get("/api/version")
def get_version_endpoint() -> Dict[str, str]:
    return {
        "version": APP_VERSION,
        "latest_version": os.environ.get("LENLU_LATEST_VERSION", APP_VERSION),
        "update_url": os.environ.get("LENLU_UPDATE_URL", UPDATE_URL),
    }

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
    with state.download_lock:
        state.pending_downloads.clear()
    proc = state.active_subprocess
    if proc:
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    broadcast_log("[system] Immediate process termination requested by user.", "warning")
    broadcast_progress({"status": "cancelled", "percent": 0.0, "title": "Terminated"})
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

def _pick_folder_powershell(initial_dir: str = "") -> Optional[str]:
    """Native Windows folder picker fallback using PowerShell and Windows Forms / Shell.Application."""
    if os.name != 'nt':
        return None
    try:
        init_arg = initial_dir.replace("'", "''") if initial_dir else ""
        ps_cmd = (
            "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$f.Description = 'Select LENLU DLP Download Folder'; "
            "$f.ShowNewFolderButton = $true; "
        )
        if init_arg:
            ps_cmd += f"$f.SelectedPath = '{init_arg}'; "
        ps_cmd += (
            "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
            "Write-Output $f.SelectedPath "
            "}"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=120
        )
        selected = res.stdout.strip()
        if selected and os.path.isdir(selected):
            return selected
    except Exception as e:
        log_warn(f"PowerShell folder picker fallback error: {e}")
    return None

def _pick_folder_webview(initial_dir: str = "") -> Optional[str]:
    """If running inside pywebview, use webview's native window dialog."""
    try:
        import webview
        if hasattr(webview, "windows") and webview.windows:
            window = webview.windows[0]
            dialog_type = getattr(webview, "FOLDER_DIALOG", 20)
            res = window.create_file_dialog(dialog_type, directory=initial_dir)
            if res and len(res) > 0:
                selected = res[0]
                if selected and os.path.isdir(selected):
                    return selected
    except Exception as e:
        log_warn(f"PyWebView folder dialog attempt failed: {e}")
    return None

def _pick_folder_tkinter(initial_dir: str = "") -> Optional[str]:
    """Use tkinter filedialog if available."""
    try:
        import tkinter as tk
        from tkinter import filedialog as tk_filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        selected = tk_filedialog.askdirectory(
            initialdir=initial_dir,
            title="Select LENLU DLP Download Folder"
        )
        root.destroy()
        if selected and os.path.isdir(selected):
            return selected
    except Exception as e:
        log_warn(f"Tkinter folder picker error: {e}")
    return None

@app.post("/api/select-download-folder")
def select_download_folder(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = load_api_settings()
    initial_dir = settings.get("downloads_dir") or get_default_downloads_dir()

    if payload and payload.get("path"):
        manual_path = os.path.abspath(payload["path"].strip())
        if not os.path.exists(manual_path):
            try:
                os.makedirs(manual_path, exist_ok=True)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Cannot create folder: {e}")
        settings["downloads_dir"] = manual_path
        save_api_settings(settings)
        return {"status": "ok", "path": manual_path}

    selected = None
    # 1. Try PyWebView native dialog if running inside PyWebView
    selected = _pick_folder_webview(initial_dir)

    # 2. Try Tkinter filedialog
    if not selected:
        selected = _pick_folder_tkinter(initial_dir)

    # 3. Try PowerShell WinForms FolderBrowserDialog on Windows
    if not selected and os.name == 'nt':
        selected = _pick_folder_powershell(initial_dir)

    if not selected:
        raise HTTPException(status_code=400, detail="Folder selection was cancelled or no folder was chosen.")

    settings["downloads_dir"] = selected
    save_api_settings(settings)
    return {"status": "ok", "path": selected}

@app.post("/api/download-thumbnail")
def download_thumbnail_endpoint(payload: Dict[str, Any]):
    url = (payload.get("url") or "").strip()
    title = (payload.get("title") or "thumbnail").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing thumbnail URL.")

    settings = load_api_settings()
    downloads_dir = settings.get("downloads_dir") or get_default_downloads_dir()
    os.makedirs(downloads_dir, exist_ok=True)

    safe_title = re.sub(r'[^a-zA-Z0-9_\- ]+', '_', title).strip() or "thumbnail"
    ext = ".jpg"
    if ".png" in url.lower():
        ext = ".png"
    elif ".webp" in url.lower():
        ext = ".webp"

    filename = f"{safe_title}_thumb{ext}"
    filepath = os.path.join(downloads_dir, filename)

    try:
        import urllib.request
        import urllib.parse
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()
            with open(filepath, "wb") as f:
                f.write(data)

        broadcast_log(f"[system] Thumbnail successfully saved: {filename}", "info")
        return {
            "status": "ok",
            "message": f"Saved thumbnail to {filename}",
            "filename": filename,
            "filepath": filepath,
            "stream_url": f"/api/thumbnail-download?url={urllib.parse.quote(url)}&title={urllib.parse.quote(safe_title)}"
        }
    except Exception as exc:
        log_error(f"Failed to download thumbnail: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to download thumbnail: {exc}")

@app.get("/api/thumbnail-download")
def stream_thumbnail_download(url: str, title: Optional[str] = "thumbnail"):
    if not url:
        raise HTTPException(status_code=400, detail="Missing thumbnail URL.")
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read()
            content_type = response.headers.get("Content-Type", "image/jpeg")
            safe_title = re.sub(r'[^a-zA-Z0-9_\- ]+', '_', title or "thumbnail").strip() or "thumbnail"
            ext = ".jpg"
            if "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"
            headers = {
                "Content-Disposition": f'attachment; filename="{safe_title}_thumb{ext}"'
            }
            return Response(content=content, media_type=content_type, headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stream thumbnail: {exc}")

@app.get("/api/app-update/check")
def check_app_update(repo: Optional[str] = None):
    current = APP_VERSION
    update_url = os.environ.get("LENLU_UPDATE_URL", UPDATE_URL)
    github_repo = repo or "lenluarun/lenlu-dlp"

    result = {
        "current_version": current,
        "latest_version": current,
        "has_update": False,
        "update_url": update_url,
        "download_url": None,
        "release_name": None,
        "release_notes": "You are currently running version v" + current + ".",
        "published_at": None,
        "assets": []
    }

    try:
        import urllib.request
        api_url = f"https://api.github.com/repos/{github_repo}/releases/latest"
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "LENLU-DLP-Update-Checker/3.1",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
            latest_tag = (data.get("tag_name") or "").lstrip("vV")
            result["latest_version"] = latest_tag or current
            result["release_name"] = data.get("name") or f"Release {latest_tag}"
            result["release_notes"] = data.get("body") or "Official GitHub Release."
            result["update_url"] = data.get("html_url") or update_url
            result["published_at"] = data.get("published_at")

            assets_list = []
            setup_download_url = None
            for asset in data.get("assets", []):
                asset_name = asset.get("name", "")
                download_url = asset.get("browser_download_url", "")
                size_mb = round(asset.get("size", 0) / (1024 * 1024), 2)
                assets_list.append({"name": asset_name, "url": download_url, "size_mb": size_mb})
                if asset_name.lower().endswith(".exe"):
                    setup_download_url = download_url

            result["assets"] = assets_list
            result["download_url"] = setup_download_url or (assets_list[0]["url"] if assets_list else None)

            if latest_tag and latest_tag != current:
                result["has_update"] = True
                result["release_notes"] = f"A new version (v{latest_tag}) is available!\n\n" + (data.get("body") or "")
    except Exception as exc:
        result["error"] = str(exc)
        result["release_notes"] = f"Latest GitHub release check ({exc}). You can download the latest installer directly below."

    return result

@app.post("/api/app-update/download")
def download_app_update(payload: Optional[Dict[str, Any]] = None):
    payload = payload or {}
    download_url = payload.get("url")
    custom_name = payload.get("filename") or "LENLU_DLP_Setup.exe"

    settings = load_api_settings()
    downloads_dir = settings.get("downloads_dir") or get_default_downloads_dir()
    os.makedirs(downloads_dir, exist_ok=True)

    target_path = os.path.join(downloads_dir, custom_name)

    if not download_url:
        # Check if local installer exists in installer/ directory as fallback
        local_installer = os.path.join(PROJECT_ROOT, "installer", "LENLU_DLP_Setup.exe")
        if os.path.exists(local_installer):
            shutil.copy2(local_installer, target_path)
            broadcast_log(f"[system] Update installer packaged: {target_path}", "info")
            return {
                "status": "ready",
                "file_path": target_path,
                "file_name": custom_name,
                "message": f"Installer ready at {target_path}"
            }
        raise HTTPException(status_code=400, detail="No download URL provided and no local installer package found.")

    try:
        import urllib.request
        broadcast_log(f"[system] Downloading application update from: {download_url}", "info")
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "Mozilla/5.0 LENLU-DLP-App"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 64 * 1024

            with open(target_path, "wb") as out_file:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    pct = round((downloaded / total_size) * 100, 1) if total_size > 0 else 0
                    broadcast_progress({
                        "status": "downloading",
                        "title": f"Downloading LENLU DLP Update ({pct}%)",
                        "percent": pct,
                        "speed_str": f"{round(downloaded / (1024*1024), 1)} MB"
                    })

        broadcast_log(f"[system] Update downloaded successfully to: {target_path}", "info")
        broadcast_progress({"status": "idle", "percent": 100.0, "title": "Update Downloaded"})
        return {
            "status": "ready",
            "file_path": target_path,
            "file_name": custom_name,
            "message": f"Update downloaded to {target_path}"
        }
    except Exception as exc:
        log_error(f"Failed to download update: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to download update: {exc}")

@app.post("/api/app-update/install")
def run_app_installer(payload: Optional[Dict[str, Any]] = None):
    payload = payload or {}
    file_path = payload.get("file_path")
    if not file_path or not os.path.exists(file_path):
        settings = load_api_settings()
        downloads_dir = settings.get("downloads_dir") or get_default_downloads_dir()
        candidate = os.path.join(downloads_dir, "LENLU_DLP_Setup.exe")
        if os.path.exists(candidate):
            file_path = candidate
        else:
            raise HTTPException(status_code=404, detail="Installer file not found on disk.")

    try:
        if os.name == 'nt':
            os.startfile(file_path)
        else:
            subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", file_path])
        return {"status": "launched", "file_path": file_path, "message": "Installer launched."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not launch installer: {exc}")

@app.get("/")
def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return "LENLU DLP Web GUI Static folder initialized. Please create index.html inside the root folder."

@app.get("/app")
@app.get("/local_host.html")
def get_app():
    # Check for the file in multiple possible locations to ensure PyInstaller compatibility
    # 1. Check in the app/gui directory
    app_path_custom = os.path.join(GUI_DIR, "index.html")
    if os.path.exists(app_path_custom):
        return FileResponse(app_path_custom)

    # 2. Check local_host.html in GUI_DIR
    app_path = os.path.join(GUI_DIR, "local_host.html")
    if os.path.exists(app_path):
        return FileResponse(app_path)

    # 3. Try index.html in GUI_DIR
    index_path = os.path.join(GUI_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    raise HTTPException(status_code=404, detail="Frontend application file not found. Please ensure app/gui/index.html or app/gui/local_host.html exists.")

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

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def print_banner(settings: dict):
    theme_name = settings.get("theme", "dark")
    Colors.apply_theme(theme_name)
    local_ip = get_local_ip()
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
    host_str = f"{local_ip}:{BACKEND_PORT}"
    open_browser = "Enabled" if settings.get("open_browser", True) else "Disabled"
    theme_display = {
        "ubuntu": "Ubuntu Purple",
        "green": "Classic Green",
        "powershell": "PowerShell Blue",
        "dark": "VS Code Dark",
    }.get(theme_name, theme_name.upper())
    print(f"  {Colors.ACCENT}▶{Colors.RESET} {Colors.BOLD}Host Address:{Colors.RESET} {Colors.TEXT}http://{host_str}{Colors.RESET}", flush=True)
    print(f"  {Colors.ACCENT}▶{Colors.RESET} {Colors.BOLD}Active Theme:{Colors.RESET} {Colors.TEXT}{theme_display}{Colors.RESET}", flush=True)
    print(f"  {Colors.ACCENT}▶{Colors.RESET} {Colors.BOLD}Auto-Browser:{Colors.RESET} {Colors.TEXT}{open_browser}{Colors.RESET}", flush=True)
    print(border, flush=True)
    print(flush=True)

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
    browser_thread = threading.Thread(target=open_browser_when_ready, daemon=True)
    browser_thread.start()
    try:
        uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT, reload=False, log_config=LOG_CONFIG)
    except KeyboardInterrupt:
        __handle_exit(None, None)
        print("")
        log_sys("Application server stopped by user interrupt.")
    except Exception as exc:
        print("")
        log_error(f"Server execution terminated: {exc}")
