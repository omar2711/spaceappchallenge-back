# pipeline/ — datos SPHEREx (B1)

Baja recortes de SPHEREx desde IRSA, los alinea y suma por **pasada × detector**, y exporta frames WebP con un `manifest.json` para la web.

## Instalación

```
python -m venv .venv
.venv/Scripts/python -m pip install -r pipeline/requirements.txt
```

## Uso (desde la raíz del repo)

```
.venv/Scripts/python -m pipeline.fetch  --target barnard --max-per-group 6   # descarga a data/raw/ (caché, se puede retomar)
.venv/Scripts/python -m pipeline.stack  --target barnard                     # sumas FITS en data/processed/
.venv/Scripts/python -m pipeline.export --target barnard                     # WebP + manifest en public-data/targets/
```

## Coordenadas arbitrarias (para la API, B3): `pipeline/custom.py`

El enunciado pide que el usuario ingrese RA/Dec y vea la serie de imágenes. `build_for_coords` produce **el mismo `manifest.json` + WebP** que los 5 objetivos (mismo schema y mismas convenciones), en `public-data/custom/<job_id>/`.

```python
from pipeline.custom import submit_custom, get_status, build_for_coords

st = submit_custom(ra=67.9105, dec=18.2327)        # fov 3', 2 exposiciones por grupo; vuelve enseguida
st = get_status(st["job_id"])                                                           # consultar cada ~2 s
# cuando st["state"] == "ready": servir public-data/ + st["manifest"]  ("custom/<job_id>/manifest.json")
```

### `submit_custom(ra, dec, fov_arcmin=3, max_exposures_per_group=2)`

- Lanza el trabajo en segundo plano y devuelve el estado inicial al instante.
- **Validación:** `ra` en [0, 360), `dec` en [−90, 90], `fov_arcmin` en (0, 6] (por defecto 3) y `max_exposures_per_group` en [1, 30] (por defecto **2**, decisión del equipo para respuestas de ~2–3 min). Con otros valores lanza `ValueError`; la API debería responder 422.
- **`job_id`:** es un hash de `(ra, dec, fov, max)` redondeados (0.36"). La misma consulta siempre da el mismo `job_id`:
  - Si el resultado ya existe, devuelve `state: "ready"` sin recalcular (caché).
  - Si ya está en cola o en proceso, devuelve el estado actual sin duplicar el trabajo.
- **Un trabajo a la vez** por proceso, para cuidar la memoria y la carga de IRSA. Los demás esperan como `pending`.

### `get_status(job_id)`

Devuelve `None` si el `job_id` no existe. Si no, un dict persistido en `data/jobs/<job_id>.json`:

```json
{
  "job_id": "c72b61a27340e", "state": "processing", "progress": 42.5, "stage": "download",
  "message": "download 40/108", "manifest": null, "error": null,
  "ra": 67.9101, "dec": 18.2328, "fov_arcmin": 3.0, "max_exposures_per_group": 6,
  "created_at": "...", "updated_at": "..."
}
```

**`state`:**

| Valor | Significado |
|---|---|
| `pending` | En cola |
| `processing` | En curso; `progress` va de 0 a 100 |
| `ready` | Terminado; `manifest` tiene la ruta relativa a `public-data/` |
| `error` | Falló; el motivo está en `error` |

**`stage`, con su tramo de `progress`:**

| Etapa | Progreso |
|---|---|
| `queued` | — |
| `query` | 0–5 % |
| `download` | 5–80 % |
| `stack` | 80–97 % |
| `export` | 97–100 % |
| `done` | 100 % |

**`error`:**

| Valor | Significado |
|---|---|
| `no_coverage` | SPHEREx todavía no observó esa posición |
| `interrupted` | El servidor se reinició a mitad del trabajo; hay que volver a llamar a `submit_custom` |
| Nombre de la excepción | Cualquier otro fallo |

### `build_for_coords(ra, dec, fov_arcmin=3, max_exposures_per_group=2, progress=None, keep_raw=False)`

- Es la versión **bloqueante**: devuelve `{"job_id", "manifest", "cached", "epochs", "frames", ...}`.
- Sirve para scripts y precálculo.
- Si no hay imágenes de SPHEREx en esa posición, lanza `LookupError`.

### Manifest de un campo libre

Igual que el de los objetivos, con estas diferencias:
- `kind: "custom"`, y `name` del tipo `"RA 67.9101, Dec +18.2328"`.
- `proper_motion_mas_yr` vale 0.
- `target_px` marca la posición pedida, que es el centro de la imagen.
- `source.max_exposures_per_group` registra el límite usado.

### Archivos y disco

| Ruta | Contenido | ¿Se conserva? |
|---|---|---|
| `public-data/custom/<id>/` | WebP + manifest (~30 KB) | Sí: es lo que sirve la API |
| `data/processed/custom/<id>/` | FITS sumados (~1 MB) | Sí, para análisis |
| `data/raw/custom/<id>/` | Recortes de IRSA (~4 MB cada uno) | No: se borran al terminar, salvo con `keep_raw=True` |

Para borrar un trabajo completo: `clear_custom(job_id)`.

### Rendimiento

- **Tiempo:** dominado por la descarga. Con 2 por grupo son ~36 recortes, ~145 MB. Las mediciones reales están en `docs/pipeline_estado.md`.
- **¿Por qué cada recorte pesa ~4 MB?** El servicio de recortes de IRSA (IBE) solo acepta `center`, `size` y `gzip`. Para SPHEREx siempre devuelve el MEF completo, incluida la tabla PSF (EPSF, ~3.9 MB), y no se puede pedir menos extensiones. `gzip=true` funciona, pero solo ahorra ~7 % (4.06 → 3.79 MB), así que no se usa. Ver <https://irsa.ipac.caltech.edu/ibe/cutouts.html>.
- **Memoria:** acotada. Se procesa grupo por grupo (pasada × detector), y solo un grupo de imágenes de 31×31 a 59×59 px está en memoria a la vez.

## Para B3 (API) y el frontend: `public-data/targets/`

```
public-data/targets/index.json                  lista de objetivos
public-data/targets/<target_id>/manifest.json   contrato (validado con pipeline/manifest.schema.json)
public-data/targets/<target_id>/S<n>_D<d>.webp  un frame por pasada (S1, S2…) y detector (D1…D6)
```

- **Video:** para un detector `d`, recorrer `detectors[d].frames` en orden. Son las pasadas del **mismo** detector, con la misma escala de brillo.
  **Nunca mezclar detectores en un mismo video:** cada detector cubre otro rango de longitud de onda.
- **Imágenes:** pequeñas (39×39 px, 6.15"/px, 4'). Hay que mostrarlas ampliadas con `image-rendering: pixelated`.
- **`target_px`:** posición esperada del objetivo en esa pasada, según Gaia. Usa coordenadas WebP: 0-based, origen arriba a la izquierda, y hacia abajo. Sirve para dibujar el marcador y la trayectoria.
- **`grid_wcs`:** sigue la convención FITS (1-based, y hacia arriba). Para convertir: `x_web = x_fits − 1` y `y_web = NAXIS2 − y_fits`.
- **`flags_fraction`:** fracción media de píxeles con banderas de contaminación (GHOST, CROSSTALK, HALO, DICHROIC). Con más de ~0.1 conviene mostrar un aviso.
- **`saturated_exposures`:** el objetivo está saturado en esas exposiciones. Afecta a la fotometría, no al video.

## Para B2 (análisis): `data/processed/<target_id>/S<n>_D<d>.fits`

No se versionan: corre `stack` o pídeme la carpeta.

| HDU | Contenido |
|---|---|
| PRIMARY | Metadatos: `EPOCH`, `DETECTOR`, `NIMAGES`, `DATE-MID`, `WAVEMIN/WAVEMAX` (µm en el objetivo), `TGT_X/TGT_Y` (0-based, convención FITS), `NSATUR`, `CONTAM` |
| IMAGE | Promedio pesado por 1/varianza, MJy/sr. Para la suma: `IMAGE × NIMAGES` |
| VARIANCE | Varianza del promedio |
| NIMAGES | Exposiciones que aportan a cada píxel |
| FILLED | > 0 donde un píxel saturado se interpoló. **No hacer fotometría ahí** |
| EXPOSURES | Una fila por exposición: `obs_id`, `mjd_mid`, `wavelength_um`, `bandwidth_um`, `saturated`, `target_x/y`, … |

- **Restas entre fechas:** todas las sumas de un objetivo comparten la misma grilla, así que se pueden restar píxel a píxel (`S3_D2 − S1_D2`).
- **Espectros:** cada exposición ve el objetivo en otra longitud de onda (`EXPOSURES.wavelength_um`). Para un espectro hay que medir en cada exposición por separado (en `data/raw/`), no en la suma.

## Limitaciones conocidas

- IRSA devuelve 503 bajo carga y cada recorte pesa ~4 MB (por la tabla EPSF). Hay que descargar con 3 hilos y con caché.
- SIMBAD TAP no respondía (404); se usa Gaia DR3 como fuente de astrometría.
- Las estrellas brillantes (Barnard, y probablemente RW Aur y R Dra) saturan: el núcleo viene NaN en IMAGE y se interpola.
- Movimiento de Barnard: ~5" (0.85 px) entre pasadas seguidas, ~10" (1.7 px) entre S1 y S3. Validado contra Gaia con un error de 0.84".
