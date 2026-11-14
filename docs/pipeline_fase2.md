# Pipeline — Fase 2: recortes, alineación y suma (Barnard, 2026-11-14)

## Cómo correrlo

```
.venv/Scripts/python -m pipeline.fetch --target barnard --max-per-group 6   # descarga (con caché, se puede retomar)
.venv/Scripts/python -m pipeline.stack --target barnard                     # sumas -> data/processed/barnard/
```

## Descarga (`pipeline/fetch.py`)

- Consulta SIA con radio de 1" (solo imágenes que contienen el objetivo). El índice se guarda en `data/raw/<target>/images.ecsv`.
- Recortes de 5' centrados en la posición del objetivo en 2026-01-01.
- **Cada recorte pesa unos 4 MB**, aunque la imagen sea de 33×33 px: la tabla EPSF dominante viene completa.
- 3 hilos (con 6, IRSA devolvía 503), reintentos con espera creciente y validación del FITS antes de aceptarlo.
- Reparto parejo entre los grupos (pasada × detector). `--max-per-group N` limita la descarga para tener todos los grupos rápido.

## Suma (`pipeline/stack.py`)

1. **Grilla común TAN** de 39×39 px a 6.15"/px (4'), con el norte arriba. Está centrada en el objetivo a la fecha media del índice completo.
2. **Fondo:** se resta `IMAGE − ZODI` y después la mediana con *sigma-clipping* del recorte.
3. **Máscara:** se descartan los bits 6, 9, 10, 11, 17, 19, 25 y 27 (NONFUNC, MISSING_DATA, HOT, COLD, PERSIST, OUTLIER, STREAK, SNOWBALL).
   No se descartan TRANSIENT, OVERFLOW, SUR_ERROR ni BLOOM, porque marcan el núcleo de las estrellas brillantes (ver `pipeline/check_flags.py`).
4. **Saturación:**
   - Varianza NaN o 0 con imagen válida: se asigna la varianza máxima del recorte, como peso bajo.
   - Imagen NaN con banderas de saturación (núcleo de Barnard en D1–D3): se rellena interpolando desde los vecinos y se registra en la capa `FILLED`.
5. **Reproyección** con `reproject_interp`; se descartan los píxeles con footprint < 0.99.
6. **Combinación:** promedio pesado por 1/varianza con *sigma-clipping* de 5σ (mediana y MAD), solo si hay 3 o más exposiciones.

## FITS de salida: `data/processed/<target>/<epoch>_D<n>.fits`

| HDU | Contenido |
|---|---|
| PRIMARY | Header: `TARGET`, `EPOCH`, `DETECTOR`, `NIMAGES`, `DATE-BEG/END/MID`, `WAVEMIN/MAX` (µm en el objetivo), `TGT_X/Y` (píxel 0-based del objetivo en `DATE-MID`), `TGT_RA/DEC`, `NSATUR`, `CONTAM`, `BADFRAC`, `REJBITS` |
| IMAGE | Promedio pesado, MJy/sr, con WCS de la grilla |
| VARIANCE | Varianza del promedio |
| NIMAGES | Exposiciones que aportan a cada píxel |
| FILLED | Exposiciones en las que el píxel fue interpolado por saturación. **No hacer fotometría donde sea > 0** |
| EXPOSURES | Tabla por exposición: `obs_id`, `collection`, `mjd_mid`, `target_x/y`, `wavelength_um`, `bandwidth_um`, `saturated`, `contam_fraction`, `bad_fraction`, `n_var_filled`, `n_holes_filled` |

Para obtener la suma literal en vez del promedio: `IMAGE × NIMAGES`.

## Resultado Barnard (181 de 358 recortes)

- S1: 17–20 exposiciones por detector. S2 y S3: 6 por detector. Las 18 combinaciones tienen datos.
- **Barnard está saturado en el 100 % de las exposiciones** (banderas en el núcleo).
- **Validación del movimiento propio S1 → S3**, con el centroide pesado por flujo en un cuadro de 7×7:

| Detector | Medido (") | Esperado por Gaia (") | Error (") |
|---|---|---|---|
| D1 | 10.07 | 10.18 | 1.26 |
| D2 | 11.04 | 10.40 | 0.74 |
| D3 | 9.56 | 10.30 | 0.88 |
| D4 | 10.50 | 10.18 | 0.80 |
| D5 | 10.49 | 10.40 | 1.13 |
| D6 | 10.44 | 10.30 | 0.79 |

Error mediano: **0.84" ≈ 0.14 px**. El movimiento medido (~1.7 px hacia el norte) coincide con Gaia.

## Pendiente

- En S2 D3 hay algunos píxeles NaN en el borde: se rellenarán al exportar el WebP.
- El resto de los recortes de Barnard se sigue bajando en segundo plano. Para incorporarlos basta con volver a correr `stack`.
