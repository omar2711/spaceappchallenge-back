# Estado del pipeline SPHEREx (B1) — 2026-11-14, 18:00

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

## Dónde está cada cosa

| Ruta | Qué es | ¿En git? |
|---|---|---|
| `pipeline/` | Código: `fetch`, `stack`, `export`, `build`, `report`, `deep`, `targets.yaml` | Sí |
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
4. **Fase 6:** `build_for_coords(ra, dec, fov)` para que B3 sirva coordenadas arbitrarias.

## Advertencias

- **IRSA devuelve 503 bajo carga y cada recorte pesa ~4 MB** (por la tabla PSF). Hay que usar ≤ 4 hilos.
- **SIMBAD TAP no respondía.** La astrometría está fija en `targets.yaml` (Gaia DR3 para Barnard y Sesame para el resto).
- **Estrellas saturadas** (Barnard, RW Aur, R Dra): el núcleo se rellena y queda marcado en la capa `FILLED`. **No hacer fotometría ahí.**
- **Cada pasada muestrea longitudes de onda distintas dentro de un detector.** Para curvas de luz rigurosas hay que comparar a la misma longitud de onda (tabla `EXPOSURES` de cada FITS).
