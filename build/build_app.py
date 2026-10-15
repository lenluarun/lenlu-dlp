import subprocess
import sys
import os

def build():
    print("🚀 Starting Professional Build Process for LENLU DLP...")

    # The exact command needed to ensure NO ModuleNotFoundError occurs
    # We use --collect-all to force PyInstaller to bundle every dependency of the key libraries
    cmd = [
        "pyinstaller",
        "--noconsole",
        "--onefile",
        "--name", "main_app",
        "--collect-all", "fastapi",
        "--collect-all", "uvicorn",
        "--collect-all", "pywebview",
        "--collect-all", "yt_dlp",
        "--add-data", "app/gui;app/gui",
        "--add-data", "app/backend;app/backend",
        "app/backend/main_app.py"
    ]

    print(f"Executing: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print("\n✅ Build Successful!")
        print("Your executable is located in: dist/main_app.exe")
        print("You can now compile your setup.iss file in Inno Setup.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build Failed: {e}")
        print("Make sure PyInstaller is installed: pip install pyinstaller")

if __name__ == "__main__":
    build()
