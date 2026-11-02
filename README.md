# LENLU DLP

LENLU DLP is a local-first media downloader with a desktop wrapper, a FastAPI backend, and a responsive browser interface powered by yt-dlp.

## What It Does

- Fetches media metadata and available streams.
- Downloads video, audio, subtitles, and merged formats.
- Supports batch downloads and a local download queue.
- Provides a searchable format matrix with codec, resolution, bitrate, and size details.
- Includes a local media library and built-in player.
- Stores downloads in a user-selected folder.
- Tracks session progress and statistics.
- Offers desktop and browser modes with responsive mobile navigation.

## Windows Installer

The packaged application is built with PyInstaller and distributed through Inno Setup. The installer includes the Python runtime and application dependencies, so end users do not need to install Python separately.

The installer creates desktop and Start Menu shortcuts, stores packaged settings under `%APPDATA%\\LENLU DLP`, and starts a local server on `127.0.0.1`.

FFmpeg is required for stream merging and audio conversion. Install it separately and add it to `PATH` unless it is bundled into the release package.

## Run From Source

```powershell
git clone https://github.com/lenluarun/lenlu-dlp.git
cd lenlu-dlp
python -m pip install -r requirements.txt
python app/backend/main_app.py
```

For browser/server mode:

```powershell
python app/backend/run_gui.py
```

Then open `http://127.0.0.1:8000/app`.

## Configuration

Settings include the download directory, default format, speed limit, proxy, cookies file, theme, automatic browser opening, and optional deployed frontend URL.

Source development stores settings in `app/gui/settings.json`. Packaged Windows builds use `%APPDATA%\\LENLU DLP\\settings.json` so preferences remain writable after installation.

## Build

```powershell
python build/build_app.py
```

The executable is written to `dist/main_app.exe`. Compile `installer/setup.iss` with Inno Setup to create the Windows installer.

## Publishing

The app exposes `/api/version` and checks GitHub Releases for newer versions. Publish the installer as a release asset named `LENLU_DLP_Setup.exe`.

Windows shows `Unknown publisher` until the executable and installer are signed with a trusted Authenticode certificate. Use an OV or EV certificate and timestamp signatures with `signtool` for public distribution.

The static site is in `landing/`. For Cloudflare Pages, use `landing` as the root directory, leave the build command empty, and use `.` as the output directory. Store installer binaries in GitHub Releases or Cloudflare R2. See [docs/CLOUDFLARE.md](docs/CLOUDFLARE.md).

## License

Distributed under the MIT License.
