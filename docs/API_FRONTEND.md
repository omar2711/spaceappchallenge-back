# API Ruta del Agua — guía para el frontend

> Generado con `python tools/gen_api_doc.py` llamando a la API real: los ejemplos son respuestas reales (listas recortadas a 2 elementos). No editar a mano: actualizar el script y regenerar.

- **Base URL local (modo demo):** `http://localhost:8000`
- **Base URL pública:** Render, ver `docs/DEPLOY.md` (plan gratuito: la primera petición tras 15 min sin uso tarda ~30–60 s; llamar antes a `/health`)
- **Documentación interactiva:** `GET /docs` (Swagger) y `GET /openapi.json`.
- **CORS:** abierto (`*`). Archivos estáticos bajo `/data/...` (la carpeta `public-data/` del repo).
- **Convención de imágenes:** los WebP tienen origen arriba a la izquierda; `target_px` = `[x, y]` en esa convención; el norte arriba y el este a la izquierda.

## Endpoints

### Salud del servicio: `GET /health`

Úsalo para despertar el servidor público antes de la demo.

Request:

```http
GET /health
```

Response `200`:

```json
{
  "status": "ok"
}
```

### Campo para coordenadas arbitrarias: `POST /custom`

Lanza (o reutiliza) la generación de un campo para RA/Dec y responde 202 al instante. Si ya existe, `state: ready` y `manifest_url`. Si no, consultar `GET /custom/{job_id}` cada ~2 s. Valores por defecto: `fov_arcmin=3` (máx. 6) y `max_exposures_per_group=2` (máx. 30). Un campo nuevo tarda ~3 min (descarga de IRSA). Entrada inválida → 422.

Request:

```http
POST /custom
Content-Type: application/json

{"ra": 83.8201, "dec": -5.3876, "fov_arcmin": 4.0}
```

Response `202`:

```json
{
  "job_id": "c2d9e7410cce7",
  "created_at": "2026-11-15T01:50:25+00:00",
  "state": "ready",
  "progress": 100.0,
  "stage": "done",
  "message": "cached",
  "manifest": "custom/c2d9e7410cce7/manifest.json",
  "ra": 83.8201,
  "dec": -5.3876,
  "fov_arcmin": 4.0,
  "max_exposures_per_group": 2,
  "updated_at": "2026-11-15T02:29:16+00:00",
  "manifest_url": "/data/custom/c2d9e7410cce7/manifest.json"
}
```

### Estado de un campo: `GET /custom/c2d9e7410cce7`

`state`: `pending` | `processing` (con `progress` 0–100 y `stage`) | `ready` (con `manifest_url`) | `error` (`error`: `no_coverage`, `interrupted` u otro). `job_id` desconocido → 404.

Request:

```http
GET /custom/c2d9e7410cce7
```

Response `200`:

```json
{
  "job_id": "c2d9e7410cce7",
  "created_at": "2026-11-15T01:50:25+00:00",
  "state": "ready",
  "progress": 100.0,
  "stage": "done",
  "message": "cached",
  "manifest": "custom/c2d9e7410cce7/manifest.json",
  "ra": 83.8201,
  "dec": -5.3876,
  "fov_arcmin": 4.0,
  "max_exposures_per_group": 2,
  "updated_at": "2026-11-15T02:29:16+00:00",
  "manifest_url": "/data/custom/c2d9e7410cce7/manifest.json"
}
```

### Campos con espectro disponible: `GET /fields`

Campos válidos para `/spectrum`: los 5 objetivos y los presets (`hl_tau`, `trapezium`, `m42`).

Request:

```http
GET /fields
```

Response `200`:

```json
[
  {
    "field": "barnard",
    "kind": "target",
    "prepared": true
  },
  {
    "field": "eps_ind_b",
    "kind": "target",
    "prepared": true
  },
  "... (+6 más)"
]
```

### Espectro de cualquier posición dentro de un campo: `GET /spectrum`

Usa solo datos en caché; responde en ~0.1–1.5 s. `spectra[]` trae un espectro por pasada y uno `combined`; `points[]` = `wavelength_um`, `flux` (mJy), `err`, `n`, `lower_limit` (saturado → dibujar como cota). `position.target_px` es la posición dentro de las imágenes del campo (coordenadas WebP). Errores: 404 campo desconocido, 409 campo sin preparar, 422 posición fuera del campo.

Request:

```http
GET /spectrum?field=m42&ra=83.8088&dec=-5.37298&label=BN/KL
```

Response `200`:

```json
{
  "field": "m42",
  "ra": 83.8088,
  "dec": -5.37298,
  "label": "BN/KL",
  "target_px": [
    25.586,
    10.442
  ],
  "n_exposures": 35,
  "flags": {
    "contaminated": 5,
    "ok": 8,
    "saturated": 22
  },
  "spectra": [
    {
      "epoch": "S1",
      "units": "mJy",
      "binning": "native resolution (R~40 below 3.82 um, R~120 above)",
      "label": "BN/KL",
      "position": {
        "ra_deg": 83.8088,
        "dec_deg": -5.37298,
        "target_px": [
          25.586,
          10.442
        ],
        "label": "BN/KL"
      },
      "n_exposures": 8,
      "mjd_mean": 60927.844,
      "points": [
        {
          "wavelength_um": 1.557,
          "flux": 705.51234,
          "err": 38.99053,
          "n": 1,
          "lower_limit": false
        },
        {
          "wavelength_um": 1.5943,
          "flux": 820.38208,
          "err": 42.59686,
          "n": 1,
          "lower_limit": false
        },
        "... (+6 más)"
      ]
    },
    {
      "epoch": "S2",
      "units": "mJy",
      "binning": "native resolution (R~40 below 3.82 um, R~120 above)",
      "label": "BN/KL",
      "position": {
        "ra_deg": 83.8088,
        "dec_deg": -5.37298,
        "target_px": [
          25.586,
          10.442
        ],
        "label": "BN/KL"
      },
      "n_exposures": 10,
      "mjd_mean": 61105.007,
      "points": [
        {
          "wavelength_um": 1.16,
          "flux": 226.96129,
          "err": 24.24207,
          "n": 1,
          "lower_limit": false
        },
        {
          "wavelength_um": 1.1874,
          "flux": 246.64711,
          "err": 27.52896,
          "n": 1,
          "lower_limit": false
        },
        "... (+8 más)"
      ]
    },
    "... (+2 más)"
  ],
  "reference_bands": [
    {
      "label": "H2O",
      "phase": "gas",
      "wavelength_um": 1.15,
      "range_um": [
        1.1,
        1.17
      ],
      "source": "Burgasser et al. 2006 (H2O-J index window 1.140-1.165)",
      "verified": true
    },
    {
      "label": "H2O",
      "phase": "gas",
      "wavelength_um": 1.4,
      "range_um": [
        1.33,
        1.52
      ],
      "source": "Burgasser et al. 2006 (H2O-H index window 1.48-1.52, red wing of the 1.4 um band)",
      "verified": true
    },
    "... (+8 más)"
  ],
  "notes": "Forced aperture photometry (r = 12\") on cached exposures of the field at a fixed sky position (no proper motion). One point per exposure; saturated points ar...",
  "elapsed_s": 0.13
}
```

## Archivos estáticos

| Ruta | Contenido |
|---|---|
| `/data/targets/index.json` | **Índice de los 5 objetivos.** Lista de objetivos con su `manifest`. |
| `/data/targets/barnard/manifest.json` | **Manifest de un objetivo.** Contrato en `pipeline/manifest.schema.json`. Para el video: recorrer `detectors[d].frames` (mismo detector, todas las pasadas); cada `file` es un WebP relativo a la carpeta del manifest. `target_px` en coordenadas WebP (origen arriba a la izquierda). |
| `/data/targets/barnard/S1_D1.webp` | **Frame WebP.** 39×39 px (6.15"/px): mostrar ampliado con `image-rendering: pixelated`. |
| `/data/targets/eps_ind_b/analysis.json` | **Análisis (B2) de un objetivo.** Diferencias entre pasadas, imágenes profundas, curvas de luz, espectros y bandas. Contrato en `analysis/analysis.schema.json`; guía en `analysis/README.md`. |
| `/data/custom/presets.json` | **Campos de demo precalculados.** Botones de demo: enviar exactamente sus `ra`, `dec`, `fov_arcmin` y `max_exposures_per_group` a `POST /custom` para acertar la caché (o leer `manifest` directamente). |
| `/data/custom/c2d9e7410cce7/manifest.json` | **Manifest de un campo libre.** Mismo contrato que los objetivos, `kind: custom`. |
| `/data/catalogs/splices.json` | **Catálogo SPLICES (candidatas a hielo).** Formato compacto `columns` + `rows`. Son candidatas, NO detecciones (ver `important`). Colorear por `ice_priority` (1 protoestrella embebida, 2 otra YSO, 3 otra). |
| `/data/catalogs/3i_atlas.json` | **Cometa interestelar 3I/ATLAS.** Metadatos, enlaces de IRSA y resultados publicados de SPHEREx (sin imágenes procesadas). |

### `/data/targets/index.json`

Response `200`:

```json
{
  "generated_at": "2026-11-14T21:37:25+00:00",
  "targets": [
    {
      "target_id": "barnard",
      "name": "Barnard's Star",
      "kind": "high_proper_motion_star",
      "ra_deg": 269.4485025,
      "dec_deg": 4.7394201,
      "manifest": "barnard/manifest.json",
      "epochs": [
        "S1",
        "S2",
        "... (+1 más)"
      ],
      "detectors": [
        1,
        2,
        "... (+4 más)"
      ]
    },
    {
      "target_id": "eps_ind_b",
      "name": "Epsilon Indi B",
      "kind": "brown_dwarf",
      "ra_deg": 331.0441466,
      "dec_deg": -56.7828442,
      "manifest": "eps_ind_b/manifest.json",
      "epochs": [
        "S1",
        "S2",
        "... (+2 más)"
      ],
      "detectors": [
        1,
        2,
        "... (+4 más)"
      ]
    },
    "... (+3 más)"
  ]
}
```

### `/data/targets/barnard/manifest.json`

Response `200`:

```json
{
  "target_id": "barnard",
  "name": "Barnard's Star",
  "kind": "high_proper_motion_star",
  "ref_coord": {
    "ra_deg": 269.4485025,
    "dec_deg": 4.7394201,
    "epoch": "J2016.0",
    "source": "Gaia DR3 4472832130942575872"
  },
  "proper_motion_mas_yr": {
    "pmra": -801.551,
    "pmdec": 10362.394
  },
  "fov_arcmin": 3.998,
  "pixel_scale_arcsec": 6.15,
  "image_size_px": [
    39,
    39
  ],
  "grid_wcs": {
    "CTYPE1": "RA---TAN",
    "CTYPE2": "DEC--TAN",
    "CRVAL1": 269.44622827173,
    "CRVAL2": 4.7687196632577,
    "CRPIX1": 20.0,
    "CRPIX2": 20.0,
    "CDELT1": -0.0017083333333333,
    "CDELT2": 0.0017083333333333,
    "CUNIT1": "deg",
    "CUNIT2": "deg",
    "NAXIS1": 39,
    "NAXIS2": 39
  },
  "epochs": [
    {
      "id": "S1",
      "date_start": "2025-08-15T20:46:08",
      "date_end": "2025-10-01T06:23:52",
      "date_mid": "2025-09-08T01:35:00"
    },
    {
      "id": "S2",
      "date_start": "2026-03-11T02:12:34",
      "date_end": "2026-05-05T02:00:26",
      "date_mid": "2026-04-07T14:06:30"
    },
    "... (+1 más)"
  ],
  "detectors": [
    {
      "id": 1,
      "wavelength_um": [
        0.746,
        1.117
      ],
      "frames": [
        {
          "epoch": "S1",
          "file": "S1_D1.webp",
          "fits": "S1_D1.fits",
          "n_images": 24,
          "target_px": [
            18.936,
            19.832
          ],
          "flags_fraction": 0.0267,
          "saturated_exposures": 24,
          "wavelength_at_target_um": [
            0.7501,
            1.1072
          ],
          "date_mid": "2025-09-05T23:59:14.696"
        },
        {
          "epoch": "S2",
          "file": "S2_D1.webp",
          "fits": "S2_D1.fits",
          "n_images": 18,
          "target_px": [
            19.002,
            18.97
          ],
          "flags_fraction": 0.0187,
          "saturated_exposures": 18,
          "wavelength_at_target_um": [
            0.7449,
            1.0918
          ],
          "date_mid": "2026-03-11T11:18:08.018"
        },
        "... (+1 más)"
      ]
    },
    {
      "id": 2,
      "wavelength_um": [
        1.103,
        1.65
      ],
      "frames": [
        {
          "epoch": "S1",
          "file": "S1_D2.webp",
          "fits": "S1_D2.fits",
          "n_images": 18,
          "target_px": [
            18.932,
            19.879
          ],
          "flags_fraction": 0.0096,
          "saturated_exposures": 18,
          "wavelength_at_target_um": [
            1.101,
            1.6289
          ],
          "date_mid": "2025-08-26T17:40:09.900"
        },
        {
          "epoch": "S2",
          "file": "S2_D2.webp",
          "fits": "S2_D2.fits",
          "n_images": 18,
          "target_px": [
            19.004,
            18.944
          ],
          "flags_fraction": 0.0085,
          "saturated_exposures": 18,
          "wavelength_at_target_um": [
            1.1183,
            1.6291
          ],
          "date_mid": "2026-03-17T03:42:23.136"
        },
        "... (+1 más)"
      ]
    },
    "... (+4 más)"
  ],
  "stretch": {
    "method": "asinh",
    "a": 0.002,
    "percentiles": [
      2.0,
      99.5
    ],
    "per_detector_limits": {
      "1": [
        -0.0833,
        172.9208
      ],
      "2": [
        -0.1107,
        444.586
      ],
      "3": [
        -0.1006,
        327.1476
      ],
      "4": [
        -0.056,
        323.1078
      ],
      "5": [
        -0.0448,
        228.6113
      ],
      "6": [
        -0.0455,
        197.2325
      ]
    },
    "units": "MJy/sr"
  },
  "source": {
    "collections": [
      "spherex_dr1",
      "spherex_qr3"
    ],
    "n_images_available": 358,
    "generated_at": "2026-11-14T21:08:08+00:00"
  },
  "notes": "Each frame is the inverse-variance weighted mean (MJy/sr) of all exposures of one detector in one survey pass, aligned on grid_wcs. Compare frames of the SAM..."
}
```

### `/data/targets/eps_ind_b/analysis.json`

Response `200`:

```json
{
  "target_id": "eps_ind_b",
  "difference_images": [
    {
      "detector": 1,
      "from": "S1",
      "to": "S2",
      "file": "analysis/diff_S1_S2_D1.webp",
      "range": [
        -0.27613,
        0.27613
      ],
      "units": "MJy/sr",
      "flux_scale": 1.0,
      "n_ref_stars": 2,
      "scale_method": "none (k=1)",
      "mean_wavelength_um": [
        0.9716,
        0.884
      ],
      "target_residual": {
        "flux": -6.1142,
        "err": 0.1351,
        "fraction_of_target": -0.9324,
        "significance_sigma": 45.2,
        "significant": true
      },
      "dipole": {
        "separation_px": 1.585,
        "position_angle_deg": 86.8,
        "expected_shift_px": 0.357,
        "expected_position_angle_deg": 121.7,
        "note": "Negative lobe = old position, positive = new. For shifts below the PSF size the lobe separation reflects the PSF width; the direction is what validates motion."
      },
      "caveats": [
        "wavelength_mismatch",
        "few_reference_stars",
        "... (+1 más)"
      ]
    },
    {
      "detector": 1,
      "from": "S2",
      "to": "S3",
      "file": "analysis/diff_S2_S3_D1.webp",
      "range": [
        -0.27613,
        0.27613
      ],
      "units": "MJy/sr",
      "flux_scale": 0.9628,
      "n_ref_stars": 5,
      "scale_method": "field_stars",
      "mean_wavelength_um": [
        0.884,
        0.9221
      ],
      "target_residual": {
        "flux": 2.1613,
        "err": 0.0335,
        "fraction_of_target": 5.2307,
        "significance_sigma": 64.6,
        "significant": true
      },
      "dipole": {
        "separation_px": 1.775,
        "position_angle_deg": 119.3,
        "expected_shift_px": 0.394,
        "expected_position_angle_deg": 121.7,
        "note": "Negative lobe = old position, positive = new. For shifts below the PSF size the lobe separation reflects the PSF width; the direction is what validates motion."
      },
      "caveats": [
        "wavelength_mismatch",
        "moving_target"
      ]
    },
    "... (+14 más)"
  ],
  "deep_images": [
    {
      "detector": 1,
      "file": "analysis/deep_D1.webp",
      "epochs": [
        "S1",
        "S2",
        "... (+1 más)"
      ],
      "stretch": {
        "method": "asinh",
        "a": 0.002,
        "limits": [
          -0.02556,
          0.87432
        ]
      },
      "note": "Fixed-sky mean of all epochs: a moving target appears elongated along its track."
    },
    {
      "detector": 2,
      "file": "analysis/deep_D2.webp",
      "epochs": [
        "S1",
        "S2",
        "... (+2 más)"
      ],
      "stretch": {
        "method": "asinh",
        "a": 0.002,
        "limits": [
          -0.02024,
          1.48366
        ]
      },
      "note": "Fixed-sky mean of all epochs: a moving target appears elongated along its track."
    },
    "... (+4 más)"
  ],
  "light_curves": [
    {
      "detector": 1,
      "wavelength_um": [
        0.746,
        1.117
      ],
      "units": "mJy",
      "usable": true,
      "combined_snr": 186.7,
      "reference_wavelength_um": 0.8815,
      "spectral_shape_bins": 7,
      "points": [
        {
          "mjd": 60790.26313,
          "epoch": "S1",
          "wavelength_um": 0.7564,
          "flux": 0.11692,
          "err": 0.07162,
          "flux_corrected": null,
          "flag": "contaminated"
        },
        {
          "mjd": 60792.84185,
          "epoch": "S1",
          "wavelength_um": 1.0664,
          "flux": 20.19879,
          "err": 0.21176,
          "flux_corrected": 2.87167,
          "flag": "ok"
        },
        "... (+44 más)"
      ],
      "per_epoch": [
        {
          "epoch": "S2",
          "mjd": 60963.6197,
          "flux": 2.41096,
          "err": 0.48357,
          "n": 22,
          "lower_limit": false
        },
        {
          "epoch": "S3",
          "mjd": 61152.0519,
          "flux": 2.60291,
          "err": 0.46351,
          "n": 19,
          "lower_limit": false
        }
      ],
      "sub_epochs": [],
      "variability": {
        "amplitude_mag": 0.083,
        "chi2_reduced": 0.08,
        "p_value": 0.777,
        "systematic_floor": 0.03,
        "significant": false,
        "lower_limit": false,
        "note": "constant within errors"
      }
    },
    {
      "detector": 2,
      "wavelength_um": [
        1.103,
        1.65
      ],
      "units": "mJy",
      "usable": true,
      "combined_snr": 1052.4,
      "reference_wavelength_um": 1.3057,
      "spectral_shape_bins": 13,
      "points": [
        {
          "mjd": 60789.85619,
          "epoch": "S1",
          "wavelength_um": 1.5617,
          "flux": 37.42208,
          "err": 0.19978,
          "flux_corrected": 31.19478,
          "flag": "ok"
        },
        {
          "mjd": 60789.85768,
          "epoch": "S1",
          "wavelength_um": 1.5992,
          "flux": 37.31675,
          "err": 0.19994,
          "flux_corrected": 31.02288,
          "flag": "ok"
        },
        "... (+91 más)"
      ],
      "per_epoch": [
        {
          "epoch": "S1",
          "mjd": 60810.0756,
          "flux": 30.36857,
          "err": 0.67056,
          "n": 28,
          "lower_limit": false
        },
        {
          "epoch": "S2",
          "mjd": 60958.5356,
          "flux": 27.92138,
          "err": 0.82729,
          "n": 21,
          "lower_limit": false
        },
        "... (+2 más)"
      ],
      "sub_epochs": [],
      "variability": {
        "amplitude_mag": 0.091,
        "chi2_reduced": 0.85,
        "p_value": 0.464,
        "systematic_floor": 0.03,
        "significant": false,
        "lower_limit": false,
        "note": "constant within errors"
      }
    },
    "... (+4 más)"
  ],
  "spectra": [
    {
      "epoch": "S1",
      "units": "mJy",
      "binning": "native resolution (R~40 below 3.82 um, R~120 above)",
      "n_exposures": 103,
      "mjd_mean": 60805.793,
      "points": [
        {
          "wavelength_um": 1.0664,
          "flux": 20.19879,
          "err": 0.6419,
          "n": 1,
          "lower_limit": false
        },
        {
          "wavelength_um": 1.107,
          "flux": 14.23191,
          "err": 0.4388,
          "n": 2,
          "lower_limit": false
        },
        "... (+55 más)"
      ]
    },
    {
      "epoch": "S2",
      "units": "mJy",
      "binning": "native resolution (R~40 below 3.82 um, R~120 above)",
      "n_exposures": 120,
      "mjd_mean": 60958.879,
      "points": [
        {
          "wavelength_um": 0.75,
          "flux": -0.04536,
          "err": 0.07113,
          "n": 1,
          "lower_limit": false
        },
        {
          "wavelength_um": 0.7735,
          "flux": -0.00738,
          "err": 0.03816,
          "n": 4,
          "lower_limit": false
        },
        "... (+83 más)"
      ]
    },
    "... (+3 más)"
  ],
  "reference_bands": [
    {
      "label": "H2O",
      "phase": "gas",
      "wavelength_um": 1.15,
      "range_um": [
        1.1,
        1.17
      ],
      "source": "Burgasser et al. 2006 (H2O-J index window 1.140-1.165)",
      "verified": true
    },
    {
      "label": "H2O",
      "phase": "gas",
      "wavelength_um": 1.4,
      "range_um": [
        1.33,
        1.52
      ],
      "source": "Burgasser et al. 2006 (H2O-H index window 1.48-1.52, red wing of the 1.4 um band)",
      "verified": true
    },
    "... (+8 más)"
  ],
  "notes": "B2 analysis on top of B1's stacks (data/processed) and cached exposures (data/raw). Difference images: k*B - A on B1's common grid; colour range shared per d...",
  "generated_at": "2026-11-15T00:38:44+00:00"
}
```

### `/data/custom/presets.json`

Response `200`:

```json
{
  "generated_at": "2026-11-15T00:29:42+00:00",
  "note": "Precomputed custom fields for the demo. Request them with exactly these ra/dec/fov_arcmin/max_exposures_per_group to hit the cache.",
  "presets": [
    {
      "id": "hl_tau",
      "name": "HL Tau",
      "description": "Young star with a protoplanetary disk (Taurus); XZ Tau is the companion to the east",
      "job_id": "cd2f34edd4880",
      "ra": 67.9105,
      "dec": 18.2327,
      "fov_arcmin": 3.0,
      "max_exposures_per_group": 2,
      "manifest": "custom/cd2f34edd4880/manifest.json"
    },
    {
      "id": "trapezium",
      "name": "Trapecio de Orión (θ¹ Ori C)",
      "description": "Young cluster lighting up the Orion Nebula; BN/KL infrared source appears at 2.5-5 µm (D4-D6)",
      "job_id": "c849cdb29dee1",
      "ra": 83.8186,
      "dec": -5.3897,
      "fov_arcmin": 3.0,
      "max_exposures_per_group": 2,
      "manifest": "custom/c849cdb29dee1/manifest.json"
    },
    "... (+1 más)"
  ]
}
```

### `/data/custom/c2d9e7410cce7/manifest.json`

Response `200`:

```json
{
  "target_id": "c2d9e7410cce7",
  "name": "RA 83.8201, Dec -5.3876",
  "kind": "custom",
  "ref_coord": {
    "ra_deg": 83.8201,
    "dec_deg": -5.3876,
    "epoch": "J2000.0",
    "source": "user coordinates (ICRS), no proper motion"
  },
  "proper_motion_mas_yr": {
    "pmra": 0.0,
    "pmdec": 0.0
  },
  "fov_arcmin": 3.998,
  "pixel_scale_arcsec": 6.15,
  "image_size_px": [
    39,
    39
  ],
  "grid_wcs": {
    "CTYPE1": "RA---TAN",
    "CTYPE2": "DEC--TAN",
    "CRVAL1": 83.8201,
    "CRVAL2": -5.3876,
    "CRPIX1": 20.0,
    "CRPIX2": 20.0,
    "CDELT1": -0.0017083333333333,
    "CDELT2": 0.0017083333333333,
    "CUNIT1": "deg",
    "CUNIT2": "deg",
    "NAXIS1": 39,
    "NAXIS2": 39
  },
  "epochs": [
    {
      "id": "S1",
      "date_start": "2025-09-06T03:59:40",
      "date_end": "2025-09-13T13:44:13",
      "date_mid": "2025-09-09T20:51:57"
    },
    {
      "id": "S2",
      "date_start": "2026-03-03T17:24:40",
      "date_end": "2026-03-09T10:17:39",
      "date_mid": "2026-03-06T13:51:10"
    },
    "... (+1 más)"
  ],
  "detectors": [
    {
      "id": 1,
      "wavelength_um": [
        0.746,
        1.117
      ],
      "frames": [
        {
          "epoch": "S1",
          "file": "S1_D1.webp",
          "fits": "S1_D1.fits",
          "n_images": 2,
          "target_px": [
            19.0,
            19.0
          ],
          "flags_fraction": 0.9463,
          "saturated_exposures": 2,
          "wavelength_at_target_um": [
            1.0601,
            1.0858
          ],
          "date_mid": "2025-09-06T04:00:45.454"
        },
        {
          "epoch": "S2",
          "file": "S2_D1.webp",
          "fits": "S2_D1.fits",
          "n_images": 2,
          "target_px": [
            19.0,
            19.0
          ],
          "flags_fraction": 0.7251,
          "saturated_exposures": 2,
          "wavelength_at_target_um": [
            0.7763,
            0.795
          ],
          "date_mid": "2026-03-09T10:16:35.400"
        },
        "... (+1 más)"
      ]
    },
    {
      "id": 2,
      "wavelength_um": [
        1.103,
        1.65
      ],
      "frames": [
        {
          "epoch": "S1",
          "file": "S1_D2.webp",
          "fits": "S1_D2.fits",
          "n_images": 2,
          "target_px": [
            19.0,
            19.0
          ],
          "flags_fraction": 0.0816,
          "saturated_exposures": 2,
          "wavelength_at_target_um": [
            1.5599,
            1.5975
          ],
          "date_mid": "2025-09-09T20:01:59.009"
        },
        {
          "epoch": "S2",
          "file": "S2_D2.webp",
          "fits": "S2_D2.fits",
          "n_images": 2,
          "target_px": [
            19.0,
            19.0
          ],
          "flags_fraction": 0.0025,
          "saturated_exposures": 2,
          "wavelength_at_target_um": [
            1.1577,
            1.1852
          ],
          "date_mid": "2026-03-06T13:50:45.478"
        },
        "... (+1 más)"
      ]
    },
    "... (+4 más)"
  ],
  "stretch": {
    "method": "asinh",
    "a": 0.002,
    "percentiles": [
      2.0,
      99.5
    ],
    "per_detector_limits": {
      "1": [
        -22.3328,
        2397.6795
      ],
      "2": [
        -19.5414,
        1714.7877
      ],
      "3": [
        -24.2571,
        1443.4285
      ],
      "4": [
        -40.7316,
        1371.9851
      ],
      "5": [
        -52.1575,
        6603.879
      ],
      "6": [
        -71.5408,
        9819.0078
      ]
    },
    "units": "MJy/sr"
  },
  "source": {
    "collections": [
      "spherex_dr1",
      "spherex_qr3"
    ],
    "n_images_available": 377,
    "generated_at": "2026-11-15T00:29:16+00:00",
    "max_exposures_per_group": 2
  },
  "notes": "Each frame is the inverse-variance weighted mean (MJy/sr) of all exposures of one detector in one survey pass, aligned on grid_wcs. Compare frames of the SAM..."
}
```

### `/data/catalogs/splices.json`

Response `200`:

```json
{
  "catalog": "SPLICES (SPHEREx Target List of Ice Sources)",
  "citation": "Ashby et al. 2023, ApJ; dataset doi:10.26131/IRSA554",
  "access": "IRSA Gator cone searches (catalog=splices); full catalog ~8.9 million sources (v8.6, 3.1 GB)",
  "important": "SPLICES lists sources LIKELY to show ice absorption in SPHEREx spectra; it contains no measured ice features. 'ice_priority' is our display heuristic: 1 embe...",
  "regions": [
    {
      "id": "barnard",
      "name": "Barnard's Star",
      "ra": 269.4485025,
      "dec": 4.7394201,
      "radius_arcmin": 30.0,
      "n_sources": 21
    },
    {
      "id": "eps_ind_b",
      "name": "Epsilon Indi B",
      "ra": 331.0441466,
      "dec": -56.7828442,
      "radius_arcmin": 30.0,
      "n_sources": 0
    },
    "... (+6 más)"
  ],
  "allsky": "All-sky bright embedded protostars (ML class Class I or flat spectrum, K < 9): 303 sources, 303 new",
  "n_sources": 2293,
  "columns": [
    "id",
    "ra",
    "... (+10 más)"
  ],
  "rows": [
    [
      "J011753.02+642714.2",
      19.471,
      "... (+10 más)"
    ],
    [
      "J021757.82+590551.9",
      34.491,
      "... (+10 más)"
    ],
    "... (+2291 más)"
  ],
  "generated_at": "2026-11-15T01:17:32+00:00"
}
```

### `/data/catalogs/3i_atlas.json`

Response `200`:

```json
{
  "name": "3I/ATLAS",
  "type": "interstellar comet (third known interstellar object)",
  "processed_by_us": false,
  "note": "Metadata and links only: we did not process these images. IRSA warns the comet is spatially extended at SPHEREx resolution and has low S/N at many wavelength...",
  "spherex_observations": {
    "summary": "SPHEREx observed 3I/ATLAS in August and December 2025 (pre- and post-perihelion).",
    "periods": [
      {
        "label": "Aug 2025 (pre-perihelion)",
        "survey_weeks": [
          "2025W31",
          "2025W32",
          "... (+1 más)"
        ],
        "n_spectral_images": 161
      },
      {
        "label": "Dec 2025 (post-perihelion)",
        "survey_weeks": [
          "2025W50"
        ],
        "n_spectral_images": 98
      }
    ],
    "n_spectral_images_total": 259,
    "count_source": "file list of IRSA's download script (3IATLASImages-wget.sh, dated 2026-01-14)"
  },
  "irsa": {
    "page": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html",
    "observation_table_votable": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/obscore_3I_Atlas.vot",
    "observation_table_note": "One row per spectral image: access URL, predicted comet position for the exposure (comet_ra, comet_dec) and other metadata. Can be uploaded into the IRSA Vie...",
    "download_scripts": {
      "wget": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/3IATLASImages-wget.sh",
      "curl": "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/3IATLASImages-curl.sh"
    },
    "irsa_viewer": "https://irsa.ipac.caltech.edu/irsaviewer/"
  },
  "spherex_results": [
    {
      "title": "SPHEREx Discovery of Strong Water Ice Absorption and an Extended Carbon Dioxide Coma in 3I/ATLAS",
      "reference": "Lisse et al. 2025, RNAAS 9, 242 (August 2025 data)",
      "url": "https://ui.adsabs.harvard.edu/abs/2025RNAAS...9..242L/abstract",
      "highlights": [
        "Strong water-ice absorption in the 1.5-4.0 um continuum, similar to Kuiper Belt objects and distant comets.",
        "Extended CO2 gas coma, at least ~348,000 km across in the first analysis (SPHEREx news release)."
      ]
    },
    {
      "title": "SPHEREx Pre-Perihelion Mapping of H2O, CO2, and CO in Interstellar Object 3I/ATLAS",
      "reference": "Lisse et al., ApJ Letters 2026 (arXiv:2512.07318), August 2025 data",
      "url": "https://ui.adsabs.harvard.edu/abs/2025arXiv251207318L/abstract",
      "highlights": [
        "Robust H2O gas emission at 2.7-2.8 um and CO2 at 4.23-4.27 um; tentative 13CO2 and CO.",
        "CO2 atmosphere extending to at least ~420,000 km.",
        "... (+2 más)"
      ]
    },
    "... (+1 más)"
  ],
  "news": [
    {
      "title": "SPHEREx: 3I/ATLAS CO2 coma",
      "url": "https://spherex.caltech.edu/news/3i-atlas-co2-coma"
    }
  ],
  "ruta_del_agua": "Water from outside the Solar System: SPHEREx saw water ice and water vapour, and a large carbon dioxide coma, in a comet that formed around another star.",
  "sources_checked": "2026-11-14: IRSA 3I/ATLAS page, SPHEREx news release, ADS/arXiv abstracts. Numbers are quoted, not re-derived.",
  "generated_at": "2026-11-14"
}
```
