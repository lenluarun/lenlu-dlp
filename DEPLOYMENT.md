# Deploying LENLU DLP Web Frontend (Hybrid Mode)

This guide walks you through deploying the **static frontend page** online (so you can access it via an online website URL) while keeping it connected to the **local Python backend** running on your computer for downloading videos.

---

## Step 1: Choose Your Frontend Hosting Provider

Since the frontend is a single-page static website (`index.html`), you can host it for free on Vercel, GitHub Pages, or Netlify.

### Option A: Deploying to Vercel (Recommended)

Vercel is the easiest option and takes less than 2 minutes.

1. **Install Vercel CLI** (if you don't have it):
   ```bash
   npm install -g vercel
   ```
2. **Deploy the `gui_static` folder**:
   Open PowerShell/Terminal in the project root and run:
   ```bash
   vercel lenlu_dlp_gui/gui_static
   ```
3. Follow the CLI prompts:
   - Log in or sign up to Vercel (it's free).
   - Set project name (e.g., `lenlu-dlp`).
   - Vercel will upload and give you a public URL (e.g., `https://lenlu-dlp.vercel.app`).

---

### Option B: Deploying to GitHub Pages

If you have this project hosted on GitHub, you can enable GitHub Pages:

1. Push your repository to GitHub.
2. Go to **Settings** > **Pages** inside your GitHub repository page.
3. Under **Build and deployment**, select **Deploy from a branch**.
4. Choose `main` branch and the `/lenlu_dlp_gui/gui_static` folder (or keep it as root `/` and select the branch).
5. Click **Save**. Within a few minutes, your site will be live at `https://<username>.github.io/<repository-name>`.

---

## Step 2: Running Your Local Python Server

To make the online website download videos, your local Python backend must be running on your computer.

1. Open PowerShell or Terminal on your computer.
2. Navigate to your project folder:
   ```bash
   cd "C:\Users\arune\OneDrive\Documents\github_f\lenlu dlp"
   ```
3. Boot the application server:
   ```bash
   py run_gui.py
   ```
   *(On macOS/Linux, run `python3 run_gui.py`)*
4. Minimize this terminal window. Keep it running in the background.

---

## Step 3: Accessing and Connecting

1. Open your deployed online link (e.g., `https://lenlu-dlp.vercel.app`) in your web browser.
2. The website will automatically probe your local machine at `http://127.0.0.1:8000` to locate the running backend.
3. Once detected, the connection popup will **automatically close**, and the connection status indicator at the top right will change to **ONLINE**.
4. You can now use the website online to download videos directly to your local computer's `Downloads` folder!
