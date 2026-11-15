# Decisiones del equipo

Registro de acuerdos del equipo. Agrega las nuevas decisiones arriba.

## Plantilla

### AAAA-MM-DD HH:MM — Título de la decisión

- **Contexto:** ¿qué problema o pregunta había?
- **Decisión:** ¿qué se acordó?
- **Responsables:** ¿quién lo lleva a cabo?

---

## Decisiones

### 2026-11-14 — Tema, stack y reparto

- **Contexto:** el repositorio se creó sin tema ni stack definidos.
- **Decisión:** el proyecto es **Ruta del Agua** (cielo SPHEREx → agua → Luna → Marte → Cochabamba). Stack: Python 3.11 para datos (astroquery, astropy, photutils, Skyfield), FastAPI solo para cálculos en vivo, React + Vite + TypeScript con Aladin Lite, Plotly y Leaflet. La demo va precalculada en WebP + JSON. Frontend en Vercel o GitHub Pages.
- **Reparto:** 6 módulos (datos SPHEREx, comparación y espectros, backend, frontend del cielo, frontend Luna y Marte, historia y entrega). Personas por asignar.
- **Regla de oro:** agrupar por pasada y detector (1–6) y comparar siempre el mismo detector entre fechas.

### 2026-11-15 — Contrato entre pipeline, public-data y API

- **Contexto:** B1 y B2 producen productos precalculados, mientras B3 necesita servirlos al frontend sin repetir descargas de IRSA.
- **Decisión:** `public-data/` es la fuente pública versionada para manifests, WebP y JSON de la demo. FastAPI sirve esos productos mediante `/data/` y expone metadatos bajo `/api/v1/`; los FITS, recortes y cachés de `data/` no se sirven ni se versionan.
- **Responsables:** B1 mantiene el contrato de `pipeline/manifest.schema.json`; B2 mantiene `analysis.json`; B3 mantiene el contrato documentado en [docs/api.md](./api.md).

### 2026-11-15 — Coordenadas personalizadas asíncronas y con caché

- **Contexto:** generar un campo SPHEREx arbitrario requiere descargar recortes y puede tardar varios minutos.
- **Decisión:** `POST /api/v1/custom` delega en `submit_custom`, devuelve el estado del trabajo y nunca bloquea esperando IRSA. `GET /api/v1/custom/{job_id}` consulta el progreso; se conserva un solo trabajo activo por proceso y se reutilizan resultados con el `job_id` determinista. El frontend debe preferir los presets de `public-data/custom/presets.json` durante la demo.
- **Responsables:** B3 integra la API; B1 mantiene `pipeline/custom.py` y sus límites de descarga.

### 2026-11-15 — Datos de Luna, Marte, hielo y 3I/ATLAS

- **Contexto:** estos módulos no son productos del pipeline SPHEREx y tienen datos estáticos más cálculos dependientes de fecha.
- **Decisión:** los sitios lunares, la ruta de Marte, el catálogo de hielo de demo y la ficha de 3I/ATLAS viven como JSON versionados bajo `public-data/`. Las condiciones Sol/Tierra de la Luna se calculan bajo demanda y declaran su modelo aproximado. La API no inventa una efeméride de 3I/ATLAS: hasta integrar una fuente JPL/Horizons, la respuesta indica que la posición no está disponible.
- **Responsables:** B3 mantiene los endpoints y las advertencias de precisión; B5 valida y amplía los datos científicos antes de la entrega pública.

### 2026-11-15 — Readiness, CORS y despliegue

- **Contexto:** el frontend se desplegará en un origen distinto y necesita comprobar que los artefactos públicos estén disponibles.
- **Decisión:** la API usa `API_CORS_ORIGINS`, permite `POST` para trabajos personalizados y usa `/health/ready` para comprobar los JSON mínimos. Render se configura mediante `render.yaml`; nunca se incluyen claves ni credenciales en el repositorio.
- **Responsables:** B3 configura el servicio; la persona de entrega define el dominio final del frontend.
