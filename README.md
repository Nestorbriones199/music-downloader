# 🎛️ Music Downloader

Descarga playlists completas de **YouTube** y **SoundCloud** en **MP3 320kbps** desde una interfaz web local.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-green)
![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-red)

## ✨ Características

- 🎵 YouTube y SoundCloud — playlists y tracks individuales
- 🔊 MP3 320 kbps (mejor calidad disponible)
- 🖼️ Portada incrustada en cada MP3
- 📋 Lista de canciones con progreso en tiempo real
- ⬇️ Descarga todo como ZIP desde el navegador
- 📂 Abre la carpeta directamente en el Explorador
- ⚙️ **FFmpeg se instala solo** la primera vez (no necesitas hacer nada)

## 🚀 Instalación

```bash
# 1. Clona el repo
git clone https://github.com/TU_USUARIO/music-downloader.git
cd music-downloader

# 2. Instala dependencias
pip install -r requirements.txt

# 3. Ejecuta
python app.py
```

Abre **http://localhost:5000** en tu navegador.

> La primera vez que hagas una descarga, el programa bajará FFmpeg automáticamente (~80 MB). Solo ocurre una vez.

## 📁 Estructura del proyecto

```
music-downloader/
├── app.py               # Backend Flask
├── templates/
│   └── index.html       # Interfaz web
├── requirements.txt
├── _ffmpeg/             # FFmpeg (se crea automáticamente)
└── README.md
```

## 💾 ¿Dónde se guardan los archivos?

En `Documentos/Música Descargada/<nombre de la playlist>/`

## ⚠️ Nota

Esta herramienta es para uso personal y privado. Respeta los derechos de autor.
