import webview
import threading
import sys
import os
import time
import tkinter as tk
from tkinter import messagebox
from app.backend.run_gui import app, BACKEND_HOST, BACKEND_PORT

def show_error_popup(title, message):
    """Displays a native Windows error popup to the user."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror(title, message)
        root.destroy()
    except Exception as e:
        print(f"Critical failure showing popup: {e}")

def start_backend():
    """Launches the FastAPI backend in a background thread."""
    try:
        import uvicorn
        # CRITICAL FIX: Changed '0.0.0.0' to '127.0.0.1'
        # '0.0.0.0' is often rejected by Windows WebViews as an invalid address
        # '127.0.0.1' is the standard localhost address and is widely accepted
        uvicorn.run(app, host="127.0.0.1", port=BACKEND_PORT, reload=False, log_level="error")
    except Exception as e:
        show_error_popup(
            "Backend Connection Error",
            f"Could not start the local server:\n{str(e)}\n\n"
            "Possible Cause: Another instance of LENLU DLP is already running.\n"
            "Solution: Open Task Manager and end all 'python.exe' processes."
        )

if __name__ == "__main__":
    try:
        # 1. Start Backend Process
        backend_thread = threading.Thread(target=start_backend, daemon=True)
        backend_thread.start()

        # 2. Wait for Backend to Bind to Port
        time.sleep(2)

        # 3. Create Native Window Wrapper
        # CRITICAL FIX: Changed 0.0.0.0 to 127.0.0.1 here as well
        url = f"http://127.0.0.1:{BACKEND_PORT}/app"

        window = webview.create_window(
            "LENLU DLP // MEDIA TERMINAL",
            url,
            width=1200,
            height=800,
            resizable=True,
            fullscreen=False
        )

        # 4. Force-Kill Application on Close
        def on_closing():
            os._exit(0)

        window.events.closing += on_closing

        # 5. Launch the Application
        webview.start()

    except Exception as e:
        show_error_popup("Application Crash", f"A critical error occurred during launch:\n{str(e)}")
