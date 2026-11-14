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
