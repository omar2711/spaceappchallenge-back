# analysis/ — diferencias, curvas de luz y espectros (B2)

Se construye **encima** de lo que produce el pipeline B1 (`pipeline/`), sin modificarlo:
- Lee las sumas de `data/processed/<id>/` y los recortes en caché de `data/raw/<id>/`.
- Escribe solo archivos nuevos: `public-data/targets/<id>/analysis.json` y `public-data/targets/<id>/analysis/*.webp`.

## Instalación y uso

```
.venv/Scripts/python -m pip install -r pipeline/requirements.txt -r analysis/requirements.txt
.venv/Scripts/python -m analysis.build --all                       # ~1 min con la fotometría en caché
.venv/Scripts/python -m analysis.build --target rw_aur --refresh-photometry
```

Requisitos:
- Necesita los productos de B1 en `data/` (`python -m pipeline.build ...`).
- La fotometría por exposición se guarda en `data/analysis/<id>/photometry.ecsv`. La primera corrida tarda ~30 s por objetivo y no descarga nada.

## Módulos

| Archivo | Qué hace |
|---|---|
| `diff.py` | **T1.** Diferencia `k·B − A` entre pasadas consecutivas del mismo detector, más la imagen profunda (todas las pasadas) por detector |
| `photometry.py` | Fotometría de apertura forzada en cada exposición. La posición se propaga con el movimiento propio a la fecha de cada exposición. Reutilizable para T3 (espectros) |
| `lightcurve.py` | **T2.** Curva de luz por detector, corregida por la forma espectral dentro del detector, y prueba de variabilidad |
| `build.py` | CLI. Arma `analysis.json` y lo valida con `analysis.schema.json` |

## Cómo lo consume el frontend

`public-data/targets/<id>/analysis.json` (contrato en `analysis/analysis.schema.json`):

### Diferencias (`difference_images[]`)

- **Archivo:** `file` (WebP RGB de 39×39, en la misma grilla y orientación que los frames de B1, así que `target_px` del manifest sirve igual).
- **Colores:** azul = más débil o posición vieja; blanco = sin cambio; rojo = más brillante o posición nueva.
- **`range`:** el rango simétrico en MJy/sr, compartido por todos los pares de un detector.
- **`caveats`:** avisos para mostrar en la interfaz:
  - `wavelength_mismatch`: las dos pasadas muestrearon longitudes de onda distintas dentro del detector, así que el residuo del objetivo puede ser espectral y no variabilidad.
  - `saturated_target`: núcleo saturado.
  - `few_reference_stars`: escala de flujo k = 1, sin estrellas de referencia.
  - `moving_target`: el objetivo se mueve; se espera un dipolo rojo/azul.
- **`dipole`:** dirección del movimiento medida contra la esperada, como ángulo de posición en grados (desde el norte hacia el este).

### Imágenes profundas (`deep_images[]`)

- Promedio de todas las pasadas por detector, en escala de grises.
- Un objetivo que se mueve aparece alargado.

### Curvas de luz (`light_curves[]`, una por detector)

- **`points[]`:** una medición por exposición, con `mjd`, `wavelength_um`, `flux`, `err` (mJy), `flux_corrected` (a `reference_wavelength_um`) y `flag`.
  - Para el gráfico conviene usar solo `flag == "ok"`. Si la curva tiene `variability.lower_limit`, también los `"saturated"`, marcados como cotas inferiores.
  - Valores de `flag`:
    - `ok`
    - `saturated`: núcleo perdido; el flujo es una cota inferior.
    - `contaminated`: más del 20 % de la apertura enmascarada o con banderas.
    - `blended`: hay otra fuente en la apertura.
    - `edge`: el objetivo cae en el borde del recorte.
- **`per_epoch[]`:** promedio ponderado por pasada (la curva principal).
- **`sub_epochs[]`:** bloques de ~30 días dentro de las pasadas largas, si hay datos suficientes.
- **`variability`:** `amplitude_mag`, `p_value` y `significant` (p < 0.001 con un piso sistemático del 3 %). Si `lower_limit` es verdadero, se basa en flujos saturados y la amplitud no es fiable.
- **`usable: false`:** no hay curva; el motivo está en `variability.note`.

### Espectros (`spectra[]`) — T3

- **Un espectro por pasada** (`epoch: "S1"`…) y uno **combinado** (`epoch: "combined"`).
- **`points[]`:** `wavelength_um`, `flux` (mJy), `err`, `n` (exposiciones en el tramo) y `lower_limit` (saturado). Para graficar:
  - `lower_limit: true` → triángulo hacia arriba.
  - El resto → punto con barra de error.
- **`band_measurements[]`** (solo en el combinado): `name`, `type` (`ratio` o `depth`), `value ± err`, `absorption_sigma`, `significant` (≥ 3σ) e `interpretation` (por ejemplo, que en una enana marrón la ventana "de hielo" mide gas).
- **`reference_bands[]`:** marcadores para el gráfico (`label`, `wavelength_um`, `range_um`, `source`, `verified`). **No son detecciones.**

### Espectro en coordenadas libres (base de T5)

```
python -m analysis.custom_spectrum --ra 83.80880 --dec -5.37298 --label "BN/KL" --field c2d9e7410cce7
```

- `spectrum_for_coords(ra, dec, ...)` devuelve los espectros.
- Con `--field`, se escriben en el `analysis.json` de ese campo de demo (`public-data/custom/<id>/`), con `position.target_px` dentro del campo.

## Por qué hay corrección espectral

Cada exposición de SPHEREx ve al objetivo en una longitud de onda distinta dentro del detector (filtros LVF). Si se comparan flujos sin corregir, se mezclan espectro y variabilidad. Ejemplo: en D1, R Dra parecía bajar 2.2 mag, pero parte de eso venía de que la pasada S2 muestreó solo 0.75–0.82 µm.

Por eso cada detector se ajusta como `flujo = S(λ) · g(pasada)`:
- `S(λ)` es una forma espectral por tramos (~6 exposiciones por tramo), compartida por todas las pasadas.
- `g` es la curva de luz.
