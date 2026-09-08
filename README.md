# DoVimu API

API en Python (FastAPI + yt-dlp) para inspeccionar un enlace, listar calidades y descargar **video** o **música**. Pensada para conectarse con la app Android **DoVimu** (Kotlin / Compose Multiplatform).

Úsala solo con contenido que tengas derecho a descargar. Eres responsable de respetar los términos de cada sitio y las leyes de autor de tu país.

## Qué hace

- Acepta un enlace (YouTube, TikTok, Instagram, Facebook, X y cientos de sitios que soporta [yt-dlp](https://github.com/yt-dlp/yt-dlp)).
- Devuelve título, miniatura, duración y calidades:
  - Video: `144p` … `1080p` / `2160p` según lo que exista.
  - Audio: original (m4a/webm) y MP3 128/192/320 si hay FFmpeg.
- Descarga en segundo plano con progreso (polling o Server-Sent Events).
- Entrega el archivo listo para que Android lo guarde.

Sin FFmpeg solo aparecen videos **progresivos** (audio y video ya juntos, casi siempre 360p) y el audio original. Con FFmpeg se pueden unir pistas DASH (720p/1080p) y exportar MP3.

## Arranque local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

O `.\run.ps1`.

- Docs interactivas: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

Copia `.env.example` a `.env` si quieres cambiar puerto, API key, proxy o la ruta de FFmpeg.

### FFmpeg (recomendado)

En Windows:

```powershell
winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
```

Cierra y abre la terminal para que entre en el PATH. Si queda instalado en una carpeta concreta, pon `FFMPEG_LOCATION` en `.env`.

## Endpoints

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/health` | Estado, versión y si hay FFmpeg |
| POST | `/api/v1/media/inspect` | Metadatos y calidades de un enlace |
| POST | `/api/v1/media/download` | Encola la descarga (`202` + `job_id`) |
| GET | `/api/v1/jobs/{id}` | Estado y progreso |
| GET | `/api/v1/jobs/{id}/events` | Progreso en SSE |
| GET | `/api/v1/jobs/{id}/file` | Archivo cuando `status=ready` |
| DELETE | `/api/v1/jobs/{id}` | Cancela y borra |
| GET | `/api/v1/search?q=` | Búsqueda (YouTube) |

### Inspect

```json
POST /api/v1/media/inspect
{ "url": "https://www.youtube.com/watch?v=...", "playlist": false }
```

Respuesta (resumen):

```json
{
  "source": "youtube",
  "title": "...",
  "duration": 213,
  "duration_label": "3:33",
  "thumbnail": "https://...",
  "video": [{ "id": "video:720", "label": "720p", "ext": "mp4" }],
  "audio": [{ "id": "audio:mp3:192", "label": "MP3 192 kbps", "ext": "mp3" }]
}
```

### Download

```json
POST /api/v1/media/download
{ "url": "https://...", "quality_id": "video:720" }
```

`quality_id` sale de inspect: `video:720`, `audio:best`, `audio:mp3:192`, etc.

La app Kotlin debe:

1. `inspect` → pintar ficha y lista de calidades.
2. `download` con el `quality_id` elegido.
3. Polling a `GET /api/v1/jobs/{id}` (o SSE).
4. Cuando `status` sea `ready`, bajar `GET /api/v1/jobs/{id}/file`.

Errores:

```json
{ "error": { "code": "INVALID_URL", "message": "..." } }
```

Códigos: `INVALID_URL`, `EXTRACTION_FAILED`, `UNSUPPORTED_MEDIA`, `QUALITY_NOT_AVAILABLE`, `FFMPEG_REQUIRED`, `DOWNLOAD_FAILED`, `JOB_NOT_FOUND`, `JOB_NOT_READY`, `MEDIA_TOO_LARGE`.

## Conexión con DoVimu (Android)

El proyecto de UI está en `C:\Users\aipilamunga\AndroidStudioProjects\DoVimu` (Compose Multiplatform).

| Dónde corre la app | Base URL de la API |
|--------------------|--------------------|
| Emulador Android | `http://10.0.2.2:8000` |
| Teléfono en la misma Wi‑Fi | `http://<IP-de-tu-PC>:8000` |
| Esta máquina | `http://127.0.0.1:8000` |

Más adelante hay que activar `INTERNET` y tráfico HTTP claro (`usesCleartextTraffic`) en el manifest. Eso se hace al cablear Kotlin.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Los tests no llaman a internet: yt-dlp está sustituido por fakes.

## Estructura

```
app/
  api/routes/     health, media, jobs, search
  core/           errores, validación de URL
  models/         contratos Pydantic (OpenAPI)
  services/       yt-dlp, calidades, jobs
```
