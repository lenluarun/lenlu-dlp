import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = parseInt(process.env.PORT || '3000', 10);
const HOST = '0.0.0.0';
const APP_VERSION = '3.1.0';
const UPDATE_URL = 'https://github.com/lenluarun/lenlu-dlp/releases/latest';

const GUI_DIR = path.join(__dirname, 'app', 'gui');
const DOWNLOADS_DIR = path.join(__dirname, 'downloads');
const SETTINGS_FILE = path.join(GUI_DIR, 'settings.json');

// Ensure directories exist
fs.mkdirSync(DOWNLOADS_DIR, { recursive: true });

// Seed sample files into downloads directory if empty
try {
  const existingFiles = fs.readdirSync(DOWNLOADS_DIR);
  if (existingFiles.length === 0) {
    fs.writeFileSync(
      path.join(DOWNLOADS_DIR, 'LENLU_DLP_Demo_QuickStart.mp4'),
      Buffer.from('DEMO_VIDEO_STREAM_DATA_LENLU_DLP')
    );
    fs.writeFileSync(
      path.join(DOWNLOADS_DIR, 'Developer_Master_Audio.mp3'),
      Buffer.from('DEMO_AUDIO_STREAM_DATA_LENLU_DLP')
    );
  }
} catch (e) {
  // ignore
}

// Settings state
function loadSettings() {
  const defaults = {
    downloads_dir: DOWNLOADS_DIR,
    format_default: 'best',
    sponsorblock: false,
    embed_metadata: true,
    embed_thumbnail: true,
    speed_limit: 'none',
    proxy: '',
    cookies_file: '',
    theme: 'dark',
    open_browser: true,
    deployed_frontend_url: '',
  };
  try {
    if (fs.existsSync(SETTINGS_FILE)) {
      const data = JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf-8'));
      const merged = { ...defaults, ...data };
      if (!merged.downloads_dir || !fs.existsSync(merged.downloads_dir) || merged.downloads_dir.includes('\\')) {
        merged.downloads_dir = DOWNLOADS_DIR;
      }
      return merged;
    }
  } catch (err) {
    console.error('Error loading settings:', err);
  }
  return defaults;
}

function saveSettings(settings) {
  try {
    fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2), 'utf-8');
  } catch (err) {
    console.error('Error saving settings:', err);
  }
}

function toUiSettingsResponse(settings) {
  return {
    ...settings,
    default_options: {
      outtmpl: path.join(settings.downloads_dir, '%(title)s.%(ext)s'),
      format: settings.format_default || 'best',
      ratelimit: settings.speed_limit === 'none' ? null : settings.speed_limit,
      proxy: settings.proxy || null,
      cookiefile: settings.cookies_file || null,
      cookiesfrombrowser: null,
      sponsorblock_remove: settings.sponsorblock ? ['sponsor'] : null,
      writethumbnail: Boolean(settings.embed_thumbnail),
      embedmetadata: Boolean(settings.embed_metadata),
      postprocessors: settings.embed_metadata ? [{ key: 'FFmpegMetadata' }] : [],
    },
  };
}

// Download state & SSE broadcasting
const sseClients = new Set();
const logHistory = [];
let activeTask = null;
let downloadCancelFlag = false;

function broadcastLog(message, level = 'info') {
  const event = { type: 'log', level, message };
  logHistory.push(event);
  if (logHistory.length > 500) logHistory.shift();

  const data = `event: log\ndata: ${JSON.stringify(event)}\n\n`;
  for (const client of sseClients) {
    try {
      client.write(data);
    } catch {
      sseClients.delete(client);
    }
  }
}

function broadcastProgress(progressData) {
  const data = `event: progress\ndata: ${JSON.stringify(progressData)}\n\n`;
  for (const client of sseClients) {
    try {
      client.write(data);
    } catch {
      sseClients.delete(client);
    }
  }
}

// Video metadata generator
async function fetchVideoInfo(url) {
  let title = 'Media Stream Video';
  let channel = 'YouTube Creator';
  let thumbnail = 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=60';
  let duration = 215;

  // Try oEmbed for YouTube links
  if (url.includes('youtube.com') || url.includes('youtu.be')) {
    try {
      const oembedRes = await fetch(`https://noembed.com/embed?url=${encodeURIComponent(url)}`, {
        signal: AbortSignal.timeout(4000),
      });
      if (oembedRes.ok) {
        const oe = await oembedRes.json();
        if (oe.title) title = oe.title;
        if (oe.author_name) channel = oe.author_name;
        if (oe.thumbnail_url) thumbnail = oe.thumbnail_url;
      }
    } catch {
      // Fallback if noembed is unreachable
      const cleanUrl = url.split('?')[0];
      title = `YouTube Video (${cleanUrl.slice(-11)})`;
    }
  } else if (url.includes('vimeo.com')) {
    try {
      const vRes = await fetch(`https://vimeo.com/api/oembed.json?url=${encodeURIComponent(url)}`, {
        signal: AbortSignal.timeout(4000),
      });
      if (vRes.ok) {
        const oe = await vRes.json();
        if (oe.title) title = oe.title;
        if (oe.author_name) channel = oe.author_name;
        if (oe.thumbnail_url) thumbnail = oe.thumbnail_url;
      }
    } catch {}
  } else if (!url.startsWith('http://') && !url.startsWith('https://')) {
    title = `Search Result: ${url}`;
    channel = 'Top Match Query';
  }

  const formats = [
    {
      format_id: 'bestvideo+bestaudio/best',
      ext: 'mp4',
      resolution: 'Auto Max Quality',
      height: 2160,
      width: 3840,
      vcodec: 'Best Video (DASH)',
      acodec: 'Best Audio (DASH)',
      filesize: 145000000,
      filesize_approx: null,
      fps: 60,
      type: 'combined',
      tbr: 25000,
      abr: null,
      vbr: null,
      asr: 48000,
      audio_channels: 2,
      dynamic_range: 'HDR/SDR',
      container: 'mp4',
      protocol: 'https',
      format_note: 'Highest quality video merged with best audio track (Auto)',
    },
    {
      format_id: 'bestvideo[height<=2160]+bestaudio/best',
      ext: 'mp4',
      resolution: '3840x2160 (4K UHD)',
      height: 2160,
      width: 3840,
      vcodec: 'AV1 / VP9',
      acodec: 'Opus / AAC',
      filesize: 120000000,
      filesize_approx: null,
      fps: 60,
      type: 'combined',
      tbr: 18500,
      abr: null,
      vbr: null,
      asr: 48000,
      audio_channels: 2,
      dynamic_range: 'HDR',
      container: 'mp4',
      protocol: 'https',
      format_note: '4K Ultra HD Pre-merged Combined MP4',
    },
    {
      format_id: 'bestvideo[height<=1440]+bestaudio/best',
      ext: 'mp4',
      resolution: '2560x1440 (1440p QHD)',
      height: 1440,
      width: 2560,
      vcodec: 'AV1 / VP9',
      acodec: 'Opus / AAC',
      filesize: 68000000,
      filesize_approx: null,
      fps: 60,
      type: 'combined',
      tbr: 10500,
      abr: null,
      vbr: null,
      asr: 48000,
      audio_channels: 2,
      dynamic_range: 'SDR',
      container: 'mp4',
      protocol: 'https',
      format_note: '1440p Quad HD Pre-merged Combined MP4',
    },
    {
      format_id: 'bestvideo[height<=1080]+bestaudio/best',
      ext: 'mp4',
      resolution: '1920x1080 (1080p FHD)',
      height: 1080,
      width: 1920,
      vcodec: 'H.264 / AV1',
      acodec: 'AAC / Opus',
      filesize: 35000000,
      filesize_approx: null,
      fps: 60,
      type: 'combined',
      tbr: 5800,
      abr: null,
      vbr: null,
      asr: 48000,
      audio_channels: 2,
      dynamic_range: 'SDR',
      container: 'mp4',
      protocol: 'https',
      format_note: '1080p Full HD Pre-merged Combined MP4',
    },
    {
      format_id: 'bestvideo[height<=720]+bestaudio/best',
      ext: 'mp4',
      resolution: '1280x720 (720p HD)',
      height: 720,
      width: 1280,
      vcodec: 'H.264 / AV1',
      acodec: 'AAC / Opus',
      filesize: 18000000,
      filesize_approx: null,
      fps: 60,
      type: 'combined',
      tbr: 3200,
      abr: null,
      vbr: null,
      asr: 48000,
      audio_channels: 2,
      dynamic_range: 'SDR',
      container: 'mp4',
      protocol: 'https',
      format_note: '720p HD Pre-merged Combined MP4',
    },
    {
      format_id: 'mp3-320',
      ext: 'mp3',
      resolution: 'audio (320 kbps)',
      height: null,
      width: null,
      vcodec: 'none',
      acodec: 'mp3 (LAME CBR)',
      filesize: 9500000,
      filesize_approx: null,
      fps: '',
      type: 'audio',
      tbr: 320,
      abr: 320,
      vbr: null,
      asr: 48000,
      audio_channels: 2,
      dynamic_range: '—',
      container: 'mp3',
      protocol: 'https',
      format_note: 'Master 320kbps CBR MP3 Audio Extraction',
    },
    {
      format_id: 'flac',
      ext: 'flac',
      resolution: 'audio (Lossless)',
      height: null,
      width: null,
      vcodec: 'none',
      acodec: 'flac',
      filesize: 28000000,
      filesize_approx: null,
      fps: '',
      type: 'audio',
      tbr: 950,
      abr: 950,
      vbr: null,
      asr: 48000,
      audio_channels: 2,
      dynamic_range: '—',
      container: 'flac',
      protocol: 'https',
      format_note: 'Audiophile 24-bit Lossless FLAC Audio',
    },
    {
      format_id: 'wav',
      ext: 'wav',
      resolution: 'audio (1411 kbps PCM)',
      height: null,
      width: null,
      vcodec: 'none',
      acodec: 'pcm_s16le',
      filesize: 42000000,
      filesize_approx: null,
      fps: '',
      type: 'audio',
      tbr: 1411,
      abr: 1411,
      vbr: null,
      asr: 48000,
      audio_channels: 2,
      dynamic_range: '—',
      container: 'wav',
      protocol: 'https',
      format_note: 'Studio Uncompressed PCM WAV Audio',
    },
    {
      format_id: 'm4a',
      ext: 'm4a',
      resolution: 'audio (256 kbps)',
      height: null,
      width: null,
      vcodec: 'none',
      acodec: 'mp4a.40.2 (AAC-LC)',
      filesize: 7800000,
      filesize_approx: null,
      fps: '',
      type: 'audio',
      tbr: 256,
      abr: 256,
      vbr: null,
      asr: 44100,
      audio_channels: 2,
      dynamic_range: '—',
      container: 'm4a',
      protocol: 'https',
      format_note: 'Apple Native 256kbps AAC M4A',
    },
  ];

  return {
    title,
    duration,
    thumbnail,
    channel,
    uploader: channel,
    description: `Media download stream prepared for ${title}. High-fidelity stream codecs ready.`,
    formats,
  };
}

// Background download runner simulation
function startDownloadJob(payload, settings, taskId) {
  downloadCancelFlag = false;
  const url = payload.url || 'Unknown URL';
  const formatId = payload.format_id || payload.format || 'best';
  const rawTitle = payload.title || (url.includes('http') ? 'Media_Download_' + taskId.slice(-4) : url);
  const safeTitle = rawTitle.replace(/[^a-zA-Z0-9_\- ]+/g, '_').trim() || 'Downloaded_Media';
  const isAudio = formatId.includes('audio') || formatId.startsWith('mp3') || formatId === 'flac' || formatId === 'wav' || formatId === 'm4a';
  const ext = isAudio ? (formatId.startsWith('mp3') ? 'mp3' : formatId) : 'mp4';
  const fileName = `${safeTitle}.${ext}`;

  activeTask = {
    id: taskId,
    url,
    title: safeTitle,
    filename: fileName,
    format: formatId,
    percent: 0,
    speed_str: '2.4 MB/s',
    eta_str: '00:08',
    _size: '0 MB / 45 MB',
    status: 'downloading',
  };

  broadcastLog(`[download] Initializing stream capture: ${url}`);
  broadcastLog(`[download] Selected profile: ${formatId} -> Output container: ${fileName}`);
  broadcastProgress(activeTask);

  let step = 0;
  const totalSteps = 10;
  const interval = setInterval(() => {
    if (downloadCancelFlag) {
      clearInterval(interval);
      activeTask = null;
      broadcastLog('[system] Download cancelled by user.', 'warning');
      broadcastProgress({ status: 'cancelled', percent: 0, title: 'Terminated' });
      return;
    }

    step++;
    const percent = Math.min(100, Math.round((step / totalSteps) * 100));
    const speedMb = (2.2 + Math.random() * 1.5).toFixed(1);
    const downloadedMb = ((percent / 100) * 45).toFixed(1);
    const etaSec = Math.max(0, Math.round((totalSteps - step) * 0.8));

    activeTask.percent = percent;
    activeTask.speed_str = `${speedMb} MB/s`;
    activeTask.eta_str = `00:${String(etaSec).padStart(2, '0')}`;
    activeTask._size = `${downloadedMb} MB / 45.0 MB`;

    broadcastProgress(activeTask);

    if (step >= totalSteps) {
      clearInterval(interval);
      activeTask.status = 'finished';
      broadcastProgress({
        ...activeTask,
        status: 'finished',
        percent: 100,
        speed_str: '0 B/s',
        eta_str: '00:00',
      });

      // Write mock file to disk in downloads_dir
      try {
        const dest = path.join(settings.downloads_dir || DOWNLOADS_DIR, fileName);
        fs.writeFileSync(dest, Buffer.from(`LENLU_DLP_DOWNLOADED_MEDIA:${safeTitle}:${formatId}`));
      } catch (err) {
        console.error('Failed to write mock file to disk:', err);
      }

      broadcastLog(`[success] 100% finished. Destination: ${fileName}`, 'success');
      setTimeout(() => {
        activeTask = null;
        broadcastProgress({ status: 'idle', percent: 0, title: '' });
      }, 2000);
    }
  }, 800);
}

// Helpers
function sendJson(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': '*',
  });
  res.end(JSON.stringify(data));
}

function parseJsonBody(req) {
  return new Promise((resolve) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
    });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch {
        resolve({});
      }
    });
  });
}

// Main HTTP Server
const server = http.createServer(async (req, res) => {
  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = parsedUrl.pathname;

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
  res.setHeader('Access-Control-Allow-Private-Network', 'true');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  // 1. SSE Stream: /api/progress/stream
  if (pathname === '/api/progress/stream') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    });
    res.flushHeaders?.();

    // Send history
    for (const log of logHistory) {
      res.write(`event: log\ndata: ${JSON.stringify(log)}\n\n`);
    }
    const currentInfo = activeTask || {
      status: 'idle',
      percent: 0,
      speed_str: '0 B/s',
      eta_str: '--:--',
      _size: '0 B / 0 B',
      filename: '',
      title: '',
    };
    res.write(`event: progress\ndata: ${JSON.stringify(currentInfo)}\n\n`);

    sseClients.add(res);

    const pingTimer = setInterval(() => {
      try {
        res.write('event: ping\ndata: {}\n\n');
      } catch {
        clearInterval(pingTimer);
        sseClients.delete(res);
      }
    }, 15000);

    req.on('close', () => {
      clearInterval(pingTimer);
      sseClients.delete(res);
    });
    return;
  }

  // 2. Settings endpoints
  if (pathname === '/api/settings') {
    if (req.method === 'GET') {
      const settings = loadSettings();
      return sendJson(res, 200, toUiSettingsResponse(settings));
    }
    if (req.method === 'POST') {
      const payload = await parseJsonBody(req);
      const settings = loadSettings();
      if (payload.downloads_dir) settings.downloads_dir = payload.downloads_dir;
      if (payload.format_default) settings.format_default = payload.format_default;
      if (payload.speed_limit !== undefined) settings.speed_limit = payload.speed_limit;
      if (payload.proxy !== undefined) settings.proxy = payload.proxy;
      if (payload.cookies_file !== undefined) settings.cookies_file = payload.cookies_file;
      if (payload.theme !== undefined) settings.theme = payload.theme;
      if (payload.open_browser !== undefined) settings.open_browser = payload.open_browser;
      if (payload.deployed_frontend_url !== undefined) settings.deployed_frontend_url = payload.deployed_frontend_url;
      if (payload.sponsorblock !== undefined) settings.sponsorblock = payload.sponsorblock;
      if (payload.embed_metadata !== undefined) settings.embed_metadata = payload.embed_metadata;
      if (payload.embed_thumbnail !== undefined) settings.embed_thumbnail = payload.embed_thumbnail;
      saveSettings(settings);
      return sendJson(res, 200, toUiSettingsResponse(settings));
    }
  }

  // 3. Version endpoint
  if (pathname === '/api/version') {
    return sendJson(res, 200, {
      version: APP_VERSION,
      latest_version: APP_VERSION,
      update_url: UPDATE_URL,
    });
  }

  // 4. Video metadata info
  if (pathname === '/api/info') {
    const payload = await parseJsonBody(req);
    const url = payload.url || '';
    if (!url) {
      return sendJson(res, 400, { detail: 'Missing media URL.' });
    }
    try {
      const info = await fetchVideoInfo(url);
      return sendJson(res, 200, info);
    } catch (err) {
      return sendJson(res, 400, { detail: String(err.message || err) });
    }
  }

  // 5. Download trigger
  if (pathname === '/api/download') {
    const payload = await parseJsonBody(req);
    const settings = loadSettings();
    const taskId = String(Date.now());
    startDownloadJob(payload, settings, taskId);
    return sendJson(res, 200, { status: 'started', task_id: taskId });
  }

  // 6. Cancel download
  if (pathname === '/api/cancel') {
    downloadCancelFlag = true;
    return sendJson(res, 200, { status: 'cancelling', message: 'Cancellation requested.' });
  }

  // 7. Task status
  if (pathname === '/api/task-status') {
    return sendJson(res, 200, {
      running: activeTask !== null,
      task_id: activeTask?.id || null,
      pending_count: 0,
      status: activeTask?.status || 'idle',
      title: activeTask?.title || '',
      percent: activeTask?.percent || 0,
    });
  }

  // 8. Library
  if (pathname === '/api/library') {
    const settings = loadSettings();
    const folder = settings.downloads_dir || DOWNLOADS_DIR;
    const files = [];
    try {
      if (fs.existsSync(folder)) {
        const entries = fs.readdirSync(folder, { withFileTypes: true });
        for (const entry of entries) {
          if (!entry.isFile()) continue;
          if (entry.name.endsWith('.part') || entry.name.endsWith('.tmp')) continue;
          const stat = fs.statSync(path.join(folder, entry.name));
          files.push({
            name: entry.name,
            size: stat.size,
            modified: stat.mtimeMs / 1000,
          });
        }
      }
    } catch (err) {
      console.error('Error reading library:', err);
    }
    files.sort((a, b) => b.modified - a.modified);
    return sendJson(res, 200, { folder, files });
  }

  // Library delete single
  if (pathname.startsWith('/api/library/') && req.method === 'DELETE') {
    const rawName = pathname.replace('/api/library/', '');
    const safeName = path.basename(decodeURIComponent(rawName));
    const settings = loadSettings();
    const targetFile = path.join(settings.downloads_dir || DOWNLOADS_DIR, safeName);
    try {
      if (fs.existsSync(targetFile)) {
        fs.unlinkSync(targetFile);
        return sendJson(res, 200, { status: 'deleted', name: safeName });
      }
      return sendJson(res, 404, { detail: 'File not found' });
    } catch (err) {
      return sendJson(res, 500, { detail: err.message });
    }
  }

  // Library clear all
  if (pathname === '/api/library/clear_all') {
    const settings = loadSettings();
    const folder = settings.downloads_dir || DOWNLOADS_DIR;
    let count = 0;
    try {
      if (fs.existsSync(folder)) {
        const list = fs.readdirSync(folder);
        for (const f of list) {
          fs.unlinkSync(path.join(folder, f));
          count++;
        }
      }
    } catch {}
    return sendJson(res, 200, { status: 'ok', removed: count });
  }

  // Play downloaded file
  if (pathname.startsWith('/api/play/')) {
    const rawName = pathname.replace('/api/play/', '');
    const safeName = path.basename(decodeURIComponent(rawName));
    const settings = loadSettings();
    const targetFile = path.join(settings.downloads_dir || DOWNLOADS_DIR, safeName);
    if (!fs.existsSync(targetFile)) {
      return sendJson(res, 404, { detail: 'File not found' });
    }

    const stat = fs.statSync(targetFile);
    const ext = path.extname(safeName).toLowerCase();
    const mimeTypes = {
      '.mp4': 'video/mp4',
      '.webm': 'video/webm',
      '.mkv': 'video/x-matroska',
      '.mp3': 'audio/mpeg',
      '.wav': 'audio/wav',
      '.flac': 'audio/flac',
      '.m4a': 'audio/mp4',
      '.opus': 'audio/opus',
      '.jpg': 'image/jpeg',
      '.png': 'image/png',
    };
    const contentType = mimeTypes[ext] || 'application/octet-stream';

    // HTTP range request support
    const range = req.headers.range;
    if (range) {
      const parts = range.replace(/bytes=/, '').split('-');
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : stat.size - 1;
      const chunksize = end - start + 1;
      const fileStream = fs.createReadStream(targetFile, { start, end });
      res.writeHead(206, {
        'Content-Range': `bytes ${start}-${end}/${stat.size}`,
        'Accept-Ranges': 'bytes',
        'Content-Length': chunksize,
        'Content-Type': contentType,
      });
      fileStream.pipe(res);
    } else {
      res.writeHead(200, {
        'Content-Length': stat.size,
        'Content-Type': contentType,
      });
      fs.createReadStream(targetFile).pipe(res);
    }
    return;
  }

  // Folder selection endpoint
  if (pathname === '/api/select-download-folder') {
    const payload = await parseJsonBody(req);
    const settings = loadSettings();
    if (payload.path) {
      settings.downloads_dir = payload.path;
      saveSettings(settings);
      fs.mkdirSync(payload.path, { recursive: true });
    }
    return sendJson(res, 200, { status: 'ok', path: settings.downloads_dir });
  }

  // Thumbnail download & stream
  if (pathname === '/api/download-thumbnail') {
    const payload = await parseJsonBody(req);
    const thumbUrl = payload.url;
    const title = (payload.title || 'thumbnail').replace(/[^a-zA-Z0-9_\-]+/g, '_');
    const filename = `${title}_thumb.jpg`;
    return sendJson(res, 200, {
      status: 'ok',
      message: `Saved thumbnail to ${filename}`,
      filename,
      filepath: path.join(DOWNLOADS_DIR, filename),
      stream_url: `/api/thumbnail-download?url=${encodeURIComponent(thumbUrl || '')}&title=${encodeURIComponent(title)}`,
    });
  }

  if (pathname === '/api/thumbnail-download') {
    const thumbUrl = parsedUrl.searchParams.get('url');
    const title = (parsedUrl.searchParams.get('title') || 'thumbnail').replace(/[^a-zA-Z0-9_\-]+/g, '_');
    if (thumbUrl && thumbUrl.startsWith('http')) {
      try {
        const resp = await fetch(thumbUrl);
        const buf = Buffer.from(await resp.arrayBuffer());
        res.writeHead(200, {
          'Content-Type': resp.headers.get('content-type') || 'image/jpeg',
          'Content-Disposition': `attachment; filename="${title}_thumb.jpg"`,
        });
        res.end(buf);
        return;
      } catch {}
    }
    // Fallback 1x1 pixel image
    res.writeHead(200, { 'Content-Type': 'image/jpeg' });
    res.end(Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46]));
    return;
  }

  // App updates
  if (pathname === '/api/app-update/check') {
    try {
      const ghRes = await fetch('https://api.github.com/repos/lenluarun/lenlu-dlp/releases/latest', {
        headers: { 'User-Agent': 'LENLU-DLP-Update-Checker/3.1' },
      });
      if (ghRes.ok) {
        const data = await ghRes.json();
        const latestTag = (data.tag_name || '').replace(/^v/i, '');
        return sendJson(res, 200, {
          current_version: APP_VERSION,
          latest_version: latestTag || APP_VERSION,
          has_update: latestTag && latestTag !== APP_VERSION,
          update_url: data.html_url || UPDATE_URL,
          download_url: data.assets?.[0]?.browser_download_url || null,
          release_name: data.name || `Release ${latestTag}`,
          release_notes: data.body || 'Official GitHub Release.',
          published_at: data.published_at,
          assets: (data.assets || []).map((a) => ({
            name: a.name,
            url: a.browser_download_url,
            size_mb: Math.round(a.size / (1024 * 1024)),
          })),
        });
      }
    } catch {}
    return sendJson(res, 200, {
      current_version: APP_VERSION,
      latest_version: APP_VERSION,
      has_update: false,
      update_url: UPDATE_URL,
      release_name: `Release v${APP_VERSION}`,
      release_notes: 'You are currently running the latest version.',
      assets: [],
    });
  }

  if (pathname === '/api/app-update/download') {
    broadcastLog('[system] Downloading application update package...', 'info');
    return sendJson(res, 200, {
      status: 'ready',
      file_path: path.join(DOWNLOADS_DIR, 'LENLU_DLP_Setup.exe'),
      file_name: 'LENLU_DLP_Setup.exe',
      message: 'Update package downloaded.',
    });
  }

  if (pathname === '/api/app-update/install') {
    return sendJson(res, 200, {
      status: 'launched',
      message: 'Installer launched. Complete the prompt to upgrade.',
    });
  }

  // Shell execute
  if (pathname === '/api/execute' || pathname === '/api/shell') {
    const payload = await parseJsonBody(req);
    const cmd = payload.command || '';
    broadcastLog(`[shell] Command accepted: ${cmd}`, 'info');
    return sendJson(res, 200, { status: 'started', message: `Command executed: ${cmd}` });
  }

  // 9. Web UI serving: / , /app , /local_host.html
  if (pathname === '/' || pathname === '/app' || pathname === '/local_host.html' || pathname === '/index.html') {
    const htmlPath = path.join(GUI_DIR, 'local_host.html');
    if (fs.existsSync(htmlPath)) {
      const htmlContent = fs.readFileSync(htmlPath, 'utf-8');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(htmlContent);
      return;
    }
  }

  // Static files in app/gui or root
  const tryPaths = [
    path.join(GUI_DIR, pathname),
    path.join(__dirname, pathname),
    path.join(__dirname, 'landing', pathname),
  ];
  for (const p of tryPaths) {
    if (fs.existsSync(p) && fs.statSync(p).isFile()) {
      const ext = path.extname(p).toLowerCase();
      const mime =
        {
          '.html': 'text/html',
          '.css': 'text/css',
          '.js': 'text/javascript',
          '.ico': 'image/x-icon',
          '.png': 'image/png',
          '.jpg': 'image/jpeg',
          '.svg': 'image/svg+xml',
          '.json': 'application/json',
        }[ext] || 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': mime });
      fs.createReadStream(p).pipe(res);
      return;
    }
  }

  // Fallback to local_host.html for SPA routes
  const fallbackPath = path.join(GUI_DIR, 'local_host.html');
  if (fs.existsSync(fallbackPath)) {
    const htmlContent = fs.readFileSync(fallbackPath, 'utf-8');
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(htmlContent);
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('404 Not Found');
});

server.listen(PORT, HOST, () => {
  console.log(`[LENLU DLP] Dev server running on http://${HOST}:${PORT}`);
  console.log(`[LENLU DLP] UI served from: ${path.join(GUI_DIR, 'local_host.html')}`);
});
