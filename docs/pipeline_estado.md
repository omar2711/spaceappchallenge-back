# Estado del pipeline SPHEREx (B1) — 2026-11-14, 20:15

## Resumen

El pipeline funciona de punta a punta. Baja recortes de SPHEREx desde IRSA, los alinea y suma por pasada × detector, y exporta WebP + `manifest.json` para la web.
**Los 5 objetivos obligatorios están exportados y validados** contra `pipeline/manifest.schema.json`.

| Objetivo | Pasadas | Frames | Exposiciones | Resultado |
|---|---|---|---|---|
| Barnard's Star | 3 | 18 | 358 (todas) | Movimiento medido 10.4" vs. 10.3" de Gaia (S1→S3), error mediano 0.95" |
| Epsilon Indi B | 4 | 22 | 458 (todas) | Movimiento ~6.0–6.5" vs. 6.5" esperado. Flujo D6 estable al 3 % (sirve de control) |
| WISE 0855-0714 | 3 | 18 | 258 (todas) | Detectada **solo en D6**, por su movimiento (7.2" vs. 8.0"). En D1–D4 hay una estrella de fondo fija |
| RW Aurigae | 3 | 18 | 108 (6 por grupo) | Variable: D1 ×2.3, D5–D6 ÷2 entre S1 y S3. Saturada |
| R Draconis | 3 | 18 | 108 (6 por grupo) | Mira: D1 cae ~2.2 mag en S2 y se recupera. Muy saturada |

## Coordenadas arbitrarias (`pipeline/custom.py`)

Cualquier RA/Dec genera el mismo `manifest.json` + WebP que los 5 objetivos, en `public-data/custom/<job_id>/`.
- Para la API: `submit_custom(...)` y `get_status(job_id)`, que lanzan el trabajo en segundo plano y devuelven su estado.
- Versión bloqueante: `build_for_coords(...)`.
- El contrato está en `pipeline/README.md`.
- **Límites:** campo de 3' por defecto (máximo 6'); **2 exposiciones por pasada × detector por defecto** (decisión del equipo; máximo 30); un trabajo a la vez por proceso.
- **Caché:** el `job_id` es un hash de `(ra, dec, fov, max)` redondeados, así que repetir una consulta no recalcula nada.

**Mediciones** (conexión doméstica, 2026-11-14):

| Prueba | Tiempo | Memoria pico | Resultado |
|---|---|---|---|
| HL Tau (67.9101, +18.2328), 3', 6/grupo, 108 recortes | **613 s** (consulta 17 s, **descarga 588 s**, suma y export ~8 s) | **138 MB** | 3 pasadas, 18 frames |
| Trapecio de Orión (83.8221, −5.3911), 2', 1/grupo, 18 recortes, en segundo plano | 96 s | — | 3 pasadas, 18 frames |
| Repetir HL Tau (caché) | 2.9 s (casi todo es importar librerías) | — | sin recálculo |
| **Por defecto de la API** (2 por grupo, 36 recortes): HL Tau 3' | **174 s** | 136 MB | 3 pasadas, 18 frames |
| Por defecto: Trapecio (θ¹ Ori C) 3' | **190 s** | 137 MB | 3 pasadas, 18 frames |
| Por defecto: M42 4' | **218 s** | 138 MB | 3 pasadas, 18 frames |

**Demo precalculada:** `public-data/custom/presets.json` lista HL Tau, el Trapecio y M42, con las `ra`, `dec`, `fov_arcmin` y `max_exposures_per_group` exactas que dan acierto de caché.
- Esos 3 campos sí están versionados; el resto de `public-data/custom/` no.
- En Orión, el objeto infrarrojo BN/KL aparece a 2.5–5 µm (D4–D6).

**¿Se puede evitar la tabla PSF?** No. El servicio IBE solo acepta `center`, `size` y `gzip`, y para SPHEREx devuelve siempre todas las extensiones. `gzip=true` solo ahorra 7 % (4.06 → 3.79 MB) y no se usa.

**El cuello de botella es la descarga.** Cada recorte pesa ~4 MB por la tabla PSF (EPSF), aunque la imagen sea pequeña, e IRSA devuelve 503 bajo carga. Para respuestas rápidas en la demo:
- usar `max_exposures_per_group` = 1–2 (~1.5–3 min), o
- precalcular las coordenadas que se vayan a mostrar.

**Regresión:** el refactor (`Spec` en `pipeline/targets.py`) reproduce Barnard bit a bit (FITS, WebP y manifest).
En eps Ind B difieren 2 píxeles de `S1_D5`, dentro del núcleo saturado rellenado: ese FITS se había generado justo antes del cambio de relleno por máximo. **Se regeneró eps Ind B completo desde la caché:** los 44 WebP, `manifest.json` y `analysis.json` salen idénticos (solo cambia `generated_at`), y ahora sus FITS son consistentes con el código.

## Dónde está cada cosa

| Ruta | Qué es | ¿En git? |
|---|---|---|
| `pipeline/` | Código: `fetch`, `stack`, `export`, `build`, `custom`, `report`, `deep`, `targets.yaml` | Sí |
| `public-data/custom/<id>/` | Campos pedidos por coordenadas (los genera la API) | No por ahora: decidir si se versionan los de la demo |
| `pipeline/README.md` | **Cómo consumir los datos (B2, B3, frontend)** | Sí |
| `public-data/targets/` | `index.json` + `manifest.json` + WebP por objetivo (419 KB) | Sí |
| `data/processed/<target>/` | FITS sumados para análisis (5.4 MB) | No: se regenera |
| `data/raw/<target>/` | Recortes de IRSA en caché (5.5 GB) | No |
| `docs/pipeline_fase*.md` | Detalle técnico y decisiones de cada fase | Sí |

## Para continuar desde una copia nueva del repo

```
python -m venv .venv
.venv/Scripts/python -m pip install -r pipeline/requirements.txt
.venv/Scripts/python -m pipeline.build --all --max-per-group 6   # ~30–40 min, ~2 GB
.venv/Scripts/python -m pipeline.report
```

- **Frontend o API:** no necesitan correr nada; `public-data/` ya está en el repo.
- **B2:** necesita los FITS de `data/processed/`. Puede regenerarlos con el comando de arriba, o pedirle la carpeta a B1 (5.4 MB).

## Pendiente

1. **Integrar a `main`.** El trabajo está en la rama `feature/pipeline-spherex` de spaceappchallenge-back; falta revisarlo y abrir un PR.
2. **Pasada completa de RW Aur y R Dra:** Claude Code detuvo la descarga por falta de memoria en el sistema. Van 263 de 335 y 108 de 539 recortes en caché. Para retomarla:
   `python -m pipeline.build --target rw_aur` y después `--target r_dra`.
3. **Decisiones abiertas:**
   - Sub-pasadas de ~30 días para las variables (R Dra tiene pasadas de 67–88 días).
   - Campo de ~10' para eps Ind B, para incluir a la estrella primaria eps Ind A.
4. ~~**Fase 6:** `build_for_coords`~~: hecho, ver la sección de coordenadas arbitrarias.
5. **B3:** conectar `submit_custom` y `get_status` a endpoints FastAPI, por ejemplo `POST /custom` y `GET /custom/{job_id}`, y servir `public-data/` como estáticos.

## Advertencias

- **IRSA devuelve 503 bajo carga y cada recorte pesa ~4 MB** (por la tabla PSF). Hay que usar ≤ 4 hilos.
- **SIMBAD TAP no respondía.** La astrometría está fija en `targets.yaml` (Gaia DR3 para Barnard y Sesame para el resto).
- **Estrellas saturadas** (Barnard, RW Aur, R Dra): el núcleo se rellena y queda marcado en la capa `FILLED`. **No hacer fotometría ahí.**
- **Cada pasada muestrea longitudes de onda distintas dentro de un detector.** Para curvas de luz rigurosas hay que comparar a la misma longitud de onda (tabla `EXPOSURES` de cada FITS).
