"""
Music Downloader — Flask backend
YouTube & SoundCloud → MP3 320kbps
"""

import os
import re
import sys
import json
import time
import shutil
import zipfile
import threading
import urllib.request
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, send_file

app = Flask(__name__)

# ── Configuración ──────────────────────────────────────────────
CALIDAD_MP3  = "320"
CARPETA_BASE = Path.home() / "Documents" / "Música Descargada"
FFMPEG_DIR   = Path(__file__).parent / "_ffmpeg"
FFMPEG_EXE   = FFMPEG_DIR / "ffmpeg.exe"
FFMPEG_URL   = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)

CARPETA_BASE.mkdir(parents=True, exist_ok=True)

# ── Estado global de descargas ─────────────────────────────────
download_sessions: dict[str, dict] = {}   # session_id → estado
sessions_lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────
def limpiar_nombre(nombre: str) -> str:
    nombre = re.sub(r'[<>:"/\\|?*]', "_", nombre)
    return nombre[:180].strip()

def detectar_plataforma(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube"
    if "soundcloud.com" in u:
        return "SoundCloud"
    return "Desconocida"

def ffmpeg_ok() -> bool:
    if shutil.which("ffmpeg"):
        return True
    if FFMPEG_EXE.exists():
        os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")
        return True
    return False

def instalar_ffmpeg(push) -> bool:
    """Descarga ffmpeg y reporta progreso mediante push(msg)."""
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    zip_tmp = FFMPEG_DIR / "ffmpeg_tmp.zip"
    push({"type": "ffmpeg", "msg": "Descargando FFmpeg (~80 MB)…"})
    try:
        def progreso(block, block_size, total):
            if total > 0:
                pct = min(100, block * block_size * 100 // total)
                push({"type": "ffmpeg_progress", "pct": pct})

        urllib.request.urlretrieve(FFMPEG_URL, zip_tmp, progreso)
        push({"type": "ffmpeg", "msg": "Extrayendo FFmpeg…"})

        with zipfile.ZipFile(zip_tmp, "r") as z:
            for member in z.namelist():
                nombre = Path(member).name
                if nombre in ("ffmpeg.exe", "ffprobe.exe"):
                    with z.open(member) as src, open(FFMPEG_DIR / nombre, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        zip_tmp.unlink(missing_ok=True)
        if not FFMPEG_EXE.exists():
            push({"type": "error", "msg": "No se encontró ffmpeg.exe en el ZIP."})
            return False

        os.environ["PATH"] = str(FFMPEG_DIR) + os.pathsep + os.environ.get("PATH", "")
        push({"type": "ffmpeg", "msg": "✅ FFmpeg instalado correctamente."})
        return True
    except Exception as e:
        push({"type": "error", "msg": f"Error instalando FFmpeg: {e}"})
        zip_tmp.unlink(missing_ok=True)
        return False


# ── Lógica de descarga en hilo ─────────────────────────────────
def run_download(session_id: str, url: str):
    import yt_dlp

    session = download_sessions[session_id]
    events  = session["events"]

    def push(obj):
        events.append(obj)

    push({"type": "status", "msg": f"Plataforma: {detectar_plataforma(url)}"})

    # FFmpeg
    if not ffmpeg_ok():
        push({"type": "status", "msg": "FFmpeg no encontrado. Instalando automáticamente…"})
        if not instalar_ffmpeg(push):
            session["done"] = True
            return

    # Metadatos
    push({"type": "status", "msg": "Obteniendo información de la playlist…"})
    try:
        ydl_flat = {"quiet": True, "extract_flat": True}
        if FFMPEG_EXE.exists():
            ydl_flat["ffmpeg_location"] = str(FFMPEG_DIR)
        with yt_dlp.YoutubeDL(ydl_flat) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            push({"type": "error", "msg": "No se pudo leer la URL."})
            session["done"] = True
            return

        es_playlist = info.get("_type") == "playlist" or "entries" in info
        titulo      = info.get("title", "Descarga")
        entradas    = list(info.get("entries", [])) if es_playlist else [info]
        total       = len(entradas)

        push({"type": "meta", "title": titulo, "total": total, "playlist": es_playlist})

    except Exception as e:
        push({"type": "error", "msg": str(e)})
        session["done"] = True
        return

    # Carpeta destino
    carpeta = CARPETA_BASE / limpiar_nombre(titulo)
    carpeta.mkdir(parents=True, exist_ok=True)
    session["carpeta"] = str(carpeta)
    push({"type": "status", "msg": f"Guardando en: {carpeta}"})

    # Hooks de progreso
    downloaded_files = []

    class MiLogger:
        def debug(self, msg):   pass
        def warning(self, msg): pass
        def error(self, msg):   push({"type": "log", "msg": msg})

    def hook(d):
        if d["status"] == "downloading":
            filename = Path(d.get("filename", "")).stem
            pct_raw  = d.get("_percent_str", "0%").strip().replace("%", "")
            try:    pct = float(pct_raw)
            except: pct = 0
            push({"type": "progress", "file": filename, "pct": round(pct)})

        elif d["status"] == "finished":
            fname = Path(d["filename"])
            # El nombre final será .mp3 después del postprocesado
            push({"type": "track_done", "file": fname.stem})
            downloaded_files.append(fname.stem)

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(carpeta / "%(playlist_index)02d - %(uploader)s - %(title)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": CALIDAD_MP3},
            {"key": "FFmpegMetadata",     "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ],
        "writethumbnail": True,
        "ignoreerrors": True,
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "logger": MiLogger(),
        "concurrent_fragment_downloads": 4,
    }
    if FFMPEG_EXE.exists():
        opts["ffmpeg_location"] = str(FFMPEG_DIR)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        # Listar mp3 reales en la carpeta
        mp3s = sorted(carpeta.glob("*.mp3"))
        tracks = [f.name for f in mp3s]
        session["tracks"]  = tracks
        session["carpeta"] = str(carpeta)
        push({"type": "done", "tracks": tracks, "carpeta": str(carpeta)})

    except Exception as e:
        push({"type": "error", "msg": str(e)})

    session["done"] = True


# ── Rutas Flask ────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def start_download():
    data = request.get_json()
    url  = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL vacía"}), 400

    import yt_dlp  # valida que esté instalado
    session_id = str(int(time.time() * 1000))
    with sessions_lock:
        download_sessions[session_id] = {
            "events": [], "done": False,
            "tracks": [], "carpeta": ""
        }

    t = threading.Thread(target=run_download, args=(session_id, url), daemon=True)
    t.start()
    return jsonify({"session_id": session_id})


@app.route("/api/events/<session_id>")
def stream_events(session_id):
    """Server-Sent Events para progreso en tiempo real."""
    def generate():
        sent = 0
        while True:
            with sessions_lock:
                session = download_sessions.get(session_id)

            if not session:
                yield "data: {\"type\":\"error\",\"msg\":\"Sesión no encontrada\"}\n\n"
                break

            events = session["events"]
            while sent < len(events):
                yield f"data: {json.dumps(events[sent])}\n\n"
                sent += 1

            if session["done"] and sent >= len(events):
                break

            time.sleep(0.3)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/download_zip/<session_id>")
def download_zip(session_id):
    """Empaqueta todos los MP3 en un ZIP y lo manda al navegador."""
    session = download_sessions.get(session_id)
    if not session or not session.get("tracks"):
        return jsonify({"error": "Sin archivos"}), 404

    carpeta = Path(session["carpeta"])
    zip_path = carpeta.parent / f"{carpeta.name}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for track in session["tracks"]:
            fp = carpeta / track
            if fp.exists():
                zf.write(fp, track)

    return send_file(zip_path, as_attachment=True, download_name=f"{carpeta.name}.zip")


@app.route("/api/open_folder/<session_id>")
def open_folder(session_id):
    """Abre la carpeta en el explorador de Windows."""
    session = download_sessions.get(session_id)
    if not session or not session.get("carpeta"):
        return jsonify({"error": "Carpeta no encontrada"}), 404
    carpeta = session["carpeta"]
    os.startfile(carpeta)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print()
    print("╔══════════════════════════════════════╗")
    print("║  🎵  Music Downloader  — iniciando   ║")
    print(f"║  Abre: http://localhost:{port}          ║")
    print("╚══════════════════════════════════════╝")
    print()
    app.run(debug=False, threaded=True, host="0.0.0.0", port=port)