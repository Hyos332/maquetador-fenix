# Maquetador MLS local

Aplicación web local para analizar un DOCX o ZIP de artículo MLS, extraer metadatos desde DOCX/OOXML, generar HTML/EPUB validables y preparar una carpeta de entrega limpia.

## Estado actual

- Backend FastAPI con pipeline reutilizable por API y CLI.
- Entrada por DOCX suelto o ZIP con DOCX/activos.
- Parser DOCX por OOXML, preservando párrafos, tablas, imágenes y bloques `w:sdt`.
- Extracción de DOI, fechas, autor, resumen/abstract, keywords, secciones, referencias e imágenes.
- Conversión de imágenes a `Figure_N.PNG`, incluyendo EMF/WMF mediante LibreOffice.
- HTML intermedio, post-procesador DOM, validador HTML y EPUB3.
- Carpeta final organizada en `deliveries/`; el ZIP queda como copia opcional.
- Page Object Playwright para el maquetador MLS externo.
- Frontend React/Vite con drag & drop, progreso, preview y descarga.

## Requisitos Ubuntu

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv libreoffice nodejs npm docker.io docker-compose-plugin
```

## Opción recomendada: Docker permanente

Esto deja la aplicación levantada en segundo plano y la vuelve a iniciar al reiniciar el PC.

```bash
docker compose up -d --build
```

Abrir:

```text
http://localhost:8095
```

Comandos útiles:

```bash
docker compose ps
docker compose logs -f
docker compose restart
docker compose down
```

La revisión IA local queda activa en Docker. El mismo comando levanta el maquetador, el contenedor `ollama` y descarga el modelo configurado en `MLS_AI_REVIEW_MODEL` dentro del volumen Docker `ollama-data`.

Por defecto usa un modelo liviano:

```yaml
MLS_AI_REVIEW_ENABLED: "true"
MLS_AI_REVIEW_MODEL: "qwen2.5:0.5b"
```

La primera vez puede tardar porque descarga el motor y el modelo; después queda guardado y arranca más rápido.

Por defecto el contenedor arranca con:

```yaml
MLS_DRY_RUN: "true"
```

Así no abre el maquetador externo y usa el HTML local determinista. Para usar Playwright contra `http://172.22.104.76:8087/`, cambia en `docker-compose.yml`:

```yaml
MLS_DRY_RUN: "false"
```

El contenedor publica la aplicación en el puerto local `8095`. Las salidas quedan persistidas en:

```text
./workspaces
./deliveries   <- aqui queda la carpeta organizada
```

## Backend

```bash
cd backend
python3 -m venv ../.venv
../.venv/bin/python -m pip install -e ".[dev]"
../.venv/bin/python -m playwright install chromium
../.venv/bin/python -m pytest
../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Variables útiles:

```bash
cp backend/.env.example backend/.env
export MLS_DRY_RUN=true
export MLS_MAQUETADOR_URL="http://172.22.104.76:8087/"
```

Con `MLS_DRY_RUN=true`, no se abre el maquetador externo: se genera HTML local determinista para desarrollar parser, validación y entrega. Con `MLS_DRY_RUN=false`, el pipeline usa Playwright y `app/automation/mls_page.py`.

## Frontend

```bash
cd frontend
npm install
npm run build
npm run dev
```

Abrir:

```text
http://localhost:5173
```

Si el backend corre en otra URL:

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## CLI

```bash
cd backend
../.venv/bin/python -m app.cli maquetar "/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Antonio Abarca_Eng.docx"
```

## API

```bash
curl -F "file=@/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip" \
  http://localhost:8000/api/jobs
```

Tambien acepta DOCX directo:

```bash
curl -F "file=@/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Antonio Abarca_Eng.docx" \
  http://localhost:8000/api/jobs
```

Luego consultar:

```bash
curl http://localhost:8000/api/jobs/<job_id>
```

Descargas:

```text
GET /api/jobs/<job_id>/html
GET /api/jobs/<job_id>/epub
GET /api/jobs/<job_id>/delivery
```

## Estructura

```text
backend/app/
  api/                 FastAPI, jobs y descargas
  automation/          Page Object Playwright del maquetador MLS
  config/journals/     YAML por revista
  models/              Modelos Pydantic
  pipeline/            ArticlePipeline
  services/            ZIP, DOCX, metadata, HTML, EPUB, validación, entrega
  utils/               Utilidades compartidas
frontend/src/
  components/          UI React
  services/            Cliente API
  types/               Tipos TypeScript
workspaces/            Trabajos temporales locales
deliveries/            Entregas limpias finales
```

## Añadir una revista

Crear un YAML en `backend/app/config/journals/<key>.yaml`:

```yaml
key: mlshnr
name: "MLS - HEALTH & NUTRITION RESEARCH (MLSHNR)"
publisher: "Multi Lingual Scientific Journals"
url: "https://www.mlsjournals.com/MLS-Health-Nutrition"
issn: "2952-2471"
logo: "logo-mlshn.svg"
image_style:
  max_width_px: 700
  max_height_px: 600
```

La lógica de negocio debe consumir `JournalConfig`; no dispersar `if journal == ...` por servicios.

## Notas del fixture Alberto

El DOCX de Alberto contiene 9 imágenes OOXML totales: 2 son cabecera/logo y 7 son contenido del artículo o tablas convertidas en imagen. El código no fuerza un conteo artificial: separa cabecera/logo de figuras reales según contexto y captions.

## Troubleshooting

Si falla Playwright:

```bash
cd backend
../.venv/bin/python -m playwright install chromium
```

Si falla una imagen EMF/WMF:

```bash
libreoffice --headless --convert-to png archivo.emf
```

Si el maquetador externo no responde:

```bash
curl -I http://172.22.104.76:8087/
```
