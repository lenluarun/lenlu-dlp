import asyncio
import json
import mimetypes
import os
import pathlib
import shutil
import socket
import sys
import threading
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

try:
    import yt_dlp
except Exception as exc:
    yt_dlp = None
    print(f"[WARNING] yt_dlp import failed: {exc}")

from starlette.middleware.base import BaseHTTPMiddleware

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
                    "Access-Control-Max-Age": "86400"
                }
                return Response(status_code=200, headers=headers)
        
        response = await call_next(request)
        origin = request.headers.get("Origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

app = FastAPI(title="LENLU DLP API")
app.add_middleware(PrivateNetworkMiddleware)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
SETTINGS_FILE = os.path.join(CURRENT_DIR, "settings.json")
STATIC_DIR = PARENT_DIR


def get_default_downloads_dir() -> str:
    try:
        downloads = pathlib.Path.home() / "Downloads"
        if downloads.exists():
            return str(downloads)
    except Exception:
        pass
    fallback = os.path.join(PARENT_DIR, "downloads", "site_downloads")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def load_settings() -> Dict[str, Any]:
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


def save_settings(settings: Dict[str, Any]) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=4)


class AppState:
    def __init__(self) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.sse_queues: set = set()
        self.active_thread: Optional[threading.Thread] = None
        self.active_subprocess = None
        self.cancel_event = threading.Event()
        self.current_download_info = {
            "status": "idle",
            "percent": "0.0%",
            "speed": "0 B/s",
            "eta": "00:00",
            "downloaded": "0 B",
            "total": "0 B",
            "filename": "",
            "title": "",
            "type": "api",
        }
        self.log_history: List[Dict[str, str]] = []


state = AppState()


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
            state.loop.call_soon_threadsafe(
                queue.put_nowait,
                {"event": "progress", "data": json.dumps(state.current_download_info)},
            )


def check_write_permission(directory: str) -> bool:
    try:
        os.makedirs(directory, exist_ok=True)
        test_file = os.path.join(directory, f".permission_test_{uuid.uuid4()}")
        with open(test_file, "w", encoding="utf-8") as handle:
            handle.write("test")
        os.remove(test_file)
        return True
    except Exception:
        return False


def check_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def check_internet_connection() -> bool:
    try:
        socket.setdefaulttimeout(3.0)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("8.8.8.8", 53)) == 0:
                return True
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("github.com", 80)) == 0
    except Exception:
        return False


def check_subprocess_permission() -> bool:
    try:
        import subprocess

        result = subprocess.run([sys.executable, "--version"], capture_output=True)
        return result.returncode == 0
    except Exception:
        return False


def format_url_or_search(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://", "ftp://", "rtmp://", "rtsp://")):
        return f"ytsearch:{value}"
    return value


@app.on_event("startup")
async def startup_event() -> None:
    state.loop = asyncio.get_running_loop()
    settings = load_settings()
    try:
        app.mount("/api/media", StaticFiles(directory=settings["downloads_dir"]), name="media")
    except Exception:
        pass


@app.get("/api/settings")
def get_settings_endpoint() -> Dict[str, Any]:
    return load_settings()


@app.get("/api/default-downloads-dir")
def get_default_downloads_dir_endpoint() -> Dict[str, Any]:
    return {"path": os.path.join(PARENT_DIR, "downloads", "site_downloads")}


@app.post("/api/settings")
def save_settings_endpoint(new_settings: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    settings.update(new_settings)
    save_settings(settings)
    try:
        app.mount("/api/media", StaticFiles(directory=settings["downloads_dir"]), name="media")
    except Exception:
        pass
    return settings


@app.post("/api/select-download-folder")
def select_download_folder() -> Dict[str, Any]:
    settings = load_settings()
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
    save_settings(settings)
    try:
        app.mount("/api/media", StaticFiles(directory=selected), name="media")
    except Exception:
        pass
    return {"status": "ok", "path": selected}


@app.get("/api/permissions/check")
def permissions_check() -> Dict[str, Any]:
    settings = load_settings()
    downloads_dir = settings.get("downloads_dir", "")
    return {
        "write": {
            "ok": check_write_permission(downloads_dir),
            "path": downloads_dir,
            "message": "Downloads folder is writable." if check_write_permission(downloads_dir) else f"Folder write permission denied: {downloads_dir}",
        },
        "ffmpeg": {
            "ok": check_ffmpeg_available(),
            "message": "ffmpeg utility is available." if check_ffmpeg_available() else "ffmpeg is missing. Merging high-quality stream formats will fail.",
        },
        "internet": {
            "ok": check_internet_connection(),
            "message": "Internet connection is active." if check_internet_connection() else "No active internet connection detected.",
        },
        "subprocess": {
            "ok": check_subprocess_permission(),
            "message": "Subprocess execution is supported." if check_subprocess_permission() else "Subprocess execution permission denied.",
        },
        "os": sys.platform,
    }


@app.get("/api/info")
def get_info(url: str):
    if yt_dlp is None:
        raise HTTPException(status_code=500, detail="yt-dlp is not installed.")

    url = format_url_or_search(url)
    if not url:
        raise HTTPException(status_code=400, detail="Empty URL or search query.")

    settings = load_settings()
    ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
    if settings.get("proxy"):
        ydl_opts["proxy"] = settings["proxy"]
    if settings.get("cookies_file") and os.path.exists(settings["cookies_file"]):
        ydl_opts["cookiefile"] = settings["cookies_file"]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
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
                    "url": item.get("url"),
                }
            )
        formats_list.reverse()
        return {
            "title": info.get("title", "Unknown Title"),
            "duration": info.get("duration") or 0,
            "thumbnail": info.get("thumbnail", ""),
            "channel": info.get("channel", "Unknown Channel"),
            "description": (info.get("description", "")[:500] + "...") if info.get("description") else "",
            "formats": formats_list,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/download")
def trigger_download(payload: Dict[str, Any]):
    if yt_dlp is None:
        raise HTTPException(status_code=500, detail="yt-dlp is not installed.")
    if state.active_thread:
        raise HTTPException(status_code=400, detail="A download task is already running.")

    url = payload.get("url")
    format_id = payload.get("format_id") or "best"
    if not url:
        raise HTTPException(status_code=400, detail="Missing video URL or search query.")
    url = format_url_or_search(url)
    settings = load_settings()

    def worker() -> None:
        state.cancel_event.clear()
        state.current_download_info.update({
            "status": "starting",
            "percent": "0.0%",
            "speed": "0 B/s",
            "eta": "--:--",
            "downloaded": "0 B",
            "total": "0 B",
            "filename": "",
            "title": "Loading...",
            "type": "api",
        })
        broadcast_progress(state.current_download_info)
        outtmpl = os.path.join(settings["downloads_dir"], "%(title)s.%(ext)s")
        ydl_opts = {
            "format": format_id,
            "outtmpl": outtmpl,
            "quiet": False,
            "noprogress": True,
            "logger": None,
        }
        if settings.get("proxy"):
            ydl_opts["proxy"] = settings["proxy"]
        if settings.get("cookies_file") and os.path.exists(settings["cookies_file"]):
            ydl_opts["cookiefile"] = settings["cookies_file"]
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            broadcast_log("[system] Download completed successfully!", "info")
            broadcast_progress({"status": "success", "percent": "100.0%"})
        except Exception as exc:
            broadcast_log(f"[error] Download failed: {exc}", "error")
            broadcast_progress({"status": "error", "percent": "0.0%"})
        finally:
            state.active_thread = None

    state.active_thread = threading.Thread(target=worker, daemon=True)
    state.active_thread.start()
    return {"status": "started"}


@app.post("/api/cancel")
def cancel_task():
    state.cancel_event.set()
    return {"status": "cancelling", "message": "Cancellation request transmitted."}


@app.get("/api/downloads")
def get_downloads_list():
    settings = load_settings()
    downloads_dir = settings["downloads_dir"]
    if not os.path.exists(downloads_dir):
        return []
    files_list = []
    playable_exts = [".mp4", ".m4v", ".webm", ".ogg", ".mp3", ".wav", ".aac", ".m4a"]
    for entry in os.scandir(downloads_dir):
        if not entry.is_file():
            continue
        ext = pathlib.Path(entry.name).suffix.lower()
        if ext in [".part", ".ytdl", ".temp"]:
            continue
        mime_type, _ = mimetypes.guess_type(entry.path)
        stat = entry.stat()
        files_list.append(
            {
                "name": entry.name,
                "size": f"{round(stat.st_size / (1024 * 1024), 1)} MB",
                "bytes": stat.st_size,
                "modified": stat.st_mtime,
                "is_playable": ext in playable_exts,
                "mime_type": mime_type or "application/octet-stream",
            }
        )
    files_list.sort(key=lambda item: item["modified"], reverse=True)
    return files_list


@app.delete("/api/downloads/{filename}")
def delete_downloaded_file(filename: str):
    settings = load_settings()
    filepath = os.path.join(settings["downloads_dir"], filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(filepath)
        base_path = os.path.splitext(filepath)[0]
        for companion_ext in [".info.json", ".jpg", ".png", ".webp", ".annotations.xml"]:
            companion = base_path + companion_ext
            if os.path.exists(companion):
                os.remove(companion)
        return {"status": "deleted"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {exc}")


@app.post("/api/downloads/clear")
def clear_all_downloads():
    settings = load_settings()
    downloads_dir = settings["downloads_dir"]
    removed = 0

    if not os.path.exists(downloads_dir):
        return {"status": "ok", "removed": 0}

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


@app.post("/api/shell")
async def trigger_shell_command(payload: Dict[str, Any]):
    command = (payload.get("command") or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="Empty command string.")
    return {"status": "started", "message": f"Command accepted: {command}"}


settings = load_settings()
try:
    app.mount("/api/media", StaticFiles(directory=settings["downloads_dir"]), name="media")
except Exception:
    pass

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
