# 📟 LENLU DLP — Retro Terminal Media Web GUI

> A premium, high-fidelity retro terminal interface for media downloading, supporting hybrid local hosting and serverless operations.

---

## ⚡ Highlights

* **📟 Immersive Retro Aesthetic**: Sleek monospace terminal design styled with custom color schemes (Modern Dark, Classic Green, PowerShell Blue, Ubuntu Purple).
* **🔄 Dual-Engine Architecture**: 
  * **Local Server Engine**: Powered by Python's **FastAPI** + **yt-dlp** for direct local filesystem downloads, high-res merging (with ffmpeg), and an integrated local media player.
  * **Serverless Engine**: Powered by public **Cobalt API** nodes for lightweight direct-to-browser downloading without needing python setup.
* **🌐 Deploy Anywhere**: Deploy the static frontend on Vercel or GitHub Pages, and securely link to your local server backend.

---

## 📥 Installation & Setup

### For End Users (Recommended)
The easiest way to get started is using the official Windows Installer.

1. **Download**: Get the latest `LENLU_DLP_Setup.exe` from the [Releases](#) section.
2. **Install**: Run the installer. It will automatically:
   - Install the application to `C:\Program Files\LENLU DLP`.
   - Create a desktop shortcut.
   - Configure the required local directories.
3. **Launch**: Double-click the **LENLU DLP** icon on your desktop. The server will start in the background and automatically open the GUI in your default browser.

### For Developers
If you prefer to run from source:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/lenluarun/lenlu-dlp.git
   cd lenlu-dlp
   ```
2. **Install dependencies**:
   ```bash
   pip install fastapi uvicorn yt-dlp
   ```
3. **Run the application**:
   ```bash
   python src/run_gui.py
   ```

---

## ⚙️ Configuration

| Parameter | Description |
| :--- | :--- |
| `downloads_dir` | Path where downloaded files are saved. |
| `theme` | Visual style (`dark`, `green`, `powershell`, `ubuntu`). |
| `cobalt_url` | Public endpoint for Serverless Mode. |

---

## 💎 Custom Keyboard Commands (CLI Console)

Type these inside the GUI footer prompt and hit **ENTER**:
* `status` - Retrieve connection status and process details.
* `clear` - Clear console feed buffer.
* `library` - View and refresh local downloads library.
* `select-folder` - Open OS folder picker to change download directory.
* `help formats` - Show quick matrix guide.

---

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.
