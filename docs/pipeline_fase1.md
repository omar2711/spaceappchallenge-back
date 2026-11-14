# Pipeline — Fase 1: exploración con Barnard's Star (2026-11-14)

Script: `pipeline/explore_barnard.py` (`.venv/Scripts/python -m pipeline.explore_barnard`)

## Fuentes

- **SIA SPHEREx:** `spherex_dr1`, `spherex_dr1_cube`, `spherex_dr1_deep`, `spherex_qr3`, `spherex_qr3_deep`. Usamos `spherex_dr1` + `spherex_qr3` (wide).
- **Astrometría:** SIMBAD TAP devolvió 404 ese día, así que usamos **Gaia DR3** (época 2016.0) por `source_id`.
  Barnard: `4472832130942575872`, pmra −801.6 / pmdec +10362.4 mas/año, plx 546.98 mas, rv −110.5 km/s.

## Movimiento propio de Barnard

| Fecha | RA | Dec | Corrimiento |
|---|---|---|---|
| 2016.0 (Gaia) | 269.448503 | 4.739420 | — |
| 2025-05 | 269.446408 | 4.766400 | 1.62' desde 2016 |
| 2026-11 | 269.446073 | 4.770724 | 15.6" = 2.5 px desde 2025-05 |

Entre pasadas consecutivas (~6 meses) se mueve unos **5" ≈ 0.85 px**. Entre S1 y S3 (~13 meses) son **≈ 11" ≈ 1.8 px**.

## Consulta SIA

- Radio 10': 419 imágenes. **Radio 1" (el objetivo cae dentro de la imagen): 358.**
- `obs_collection`: DR1 284, QR3 135. **No hay duplicados** de (`obs_id`, detector) entre DR1 y QR3.
- **Detector:** columna `energy_bandpassname` (`SPHEREx-D1` … `SPHEREx-D6`) y keyword `DETECTOR` en el header de IMAGE.
- `obs_id` (p. ej. `2026W33_2A_0594_4`) identifica la **exposición**. Una misma exposición aparece en varios detectores a la vez (pares D1/D4, D2/D5, D3/D6 ven el mismo cielo).
- Tiempo: `t_min` / `t_max` en MJD, `t_exptime` ≈ 113.6 s.
- `em_min` / `em_max` son el rango de **todo el detector**, no la longitud de onda en el objetivo:

| Detector | µm |
|---|---|
| D1 | 0.746–1.117 |
| D2 | 1.103–1.650 |
| D3 | 1.630–2.435 |
| D4 | 2.403–3.847 |
| D5 | 3.811–4.430 |
| D6 | 4.412–5.010 |

### Pasadas (corte en saltos > 60 días de `t_min`)

| Pasada | Fechas | Imágenes por detector (radio 10') |
|---|---|---|
| S1 | 2025-08-15 → 2025-10-01 | 19–27 |
| S2 | 2026-03-11 → 2026-05-05 | 20–26 |
| S3 | 2026-08-16 → 2026-09-22 | 20–27 |

Con el radio de 1" son unas 20 imágenes por detector y por pasada.

## Recortes

- Patrón oficial: `access_url + "?center={ra},{dec}d&size={grados}"`. 4' (`size=0.0667`) da **39×39 px**.
- Extensiones: 0 PRIMARY (solo `VERSION`), 1 IMAGE (MJy/sr), 2 FLAGS (int32), 3 VARIANCE, 4 ZODI, 5 EPSF (tabla), 6 WCS-WAVE (tabla).
- IMAGE header: `DETECTOR`, `DATE-OBS`, `DATE-END`, `MJD-OBS`, `MJD-AVG`, `BUNIT`. El WCS es `RA---TAN-SIP` (escala 6.158"/px).
- Longitud de onda por píxel: `WCS(header, fobj=hdul, key="W")`, luego `sip = None` y `pixel_to_world(x, y)` → (λ, ancho de banda).
  Ejemplo D3: λ = 2.307 µm en el objetivo, ancho 0.057 µm. Dentro del recorte de 4' varía apenas ~0.016 µm.
- Bits de FLAGS: el header trae `MSKNnn` (nombre) y `MSKDnn` (descripción). Bits: 0 TRANSIENT, 1 OVERFLOW, 2 SUR_ERROR, 6 NONFUNC, 7 DICHROIC, 9 MISSING_DATA, 10 HOT, 11 COLD, 12 FULLSAMPLE, 14 PHANMISS, 15 NONLINEAR, 17 PERSIST, 19 OUTLIER, 20 CROSSTALK, 21 SOURCE, 22 GHOST, 23 GHOST_FPA, 24 GHOST_EXT, 25 STREAK, 26 BLOOM, 27 SNOWBALL, 28 HALO.

## Implicaciones para la Fase 2

- **Una suma por (pasada × detector)** mezcla longitudes de onda dentro del rango del detector. Cada exposición ve el objetivo en otro λ del LVF. Sirve para el video, pero B2 necesita la λ de cada exposición: la guardaremos en el FITS.
- **Máscara propuesta:** enmascarar 0, 1, 2, 6, 9, 10, 11, 15, 17, 19, 25, 26, 27. **No** enmascarar 21 SOURCE: marca píxeles con fuentes conocidas y taparía a Barnard. 12 FULLSAMPLE es informativo. 7, 20, 22–24 y 28 quedan solo para la estadística de contaminación (`flags_fraction`).
- El movimiento entre pasadas es menor que 1 px, así que en el video Barnard se verá desplazarse poco. Para la validación conviene comparar **S1 contra S3**.
