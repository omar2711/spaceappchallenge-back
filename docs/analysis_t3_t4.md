# Análisis B2 — T3 (espectros) y T4 (catálogo SPLICES), 2026-11-14

## T3. Espectros

**Método** (`analysis/spectra.py`, `analysis/custom_spectrum.py`):
- **Espectrofotometría forzada.** Cada exposición aporta un punto (longitud de onda, flujo, error): la fotometría de T2, más la longitud de onda que ve ese píxel según WCS-WAVE.
- **Agrupación** a la resolución nativa (R ≈ 40 por debajo de 3.82 µm y R ≈ 120 por encima): un espectro por pasada y uno combinado.
- **Errores:** el mayor entre el formal y la dispersión, sumado a un piso sistemático del 3 %.
- **Saturación:** si un detector no tiene puntos `ok`, se usan los saturados marcados como `lower_limit`. Estos puntos nunca entran en las mediciones de bandas.
- **Mediciones de bandas** (`band_measurements` en el espectro combinado):
  - **Índices de cociente** al estilo Burgasser et al. 2006: H2O-J, H2O-H, CH4-H, H2O-K y CH4-K.
  - **CH4-3.3:** índice propio (3.25–3.40 / 3.90–4.10 µm).
  - **Profundidades** contra un continuo interpolado (log–log) para H₂O hielo 3.05, CO₂ 4.27 y CO 4.67.
  - Cada medición lleva su significancia en σ. `significant` = absorción ≥ 3σ.
- **`reference_bands`:** son **marcadores para el gráfico, no detecciones**. Cada uno indica su fuente y si se verificó (`verified`):
  - **Verificadas:** hielos H₂O 3.05, CO₂ 4.27 y CO 4.67 µm (página de SPHEREx); CH₄ 3.3 µm (Cushing et al. 2005); ventanas H₂O-J, H₂O-H y CH₄-H (Burgasser et al. 2006, vía Mace et al. 2013).
  - **Sin verificar en línea:** H₂O 1.9 y 2.7 µm, y CH₄-K. Son valores estándar y quedan marcados como `verified: false`.

**Resultados:**

| Objetivo | Resultado |
|---|---|
| **eps Ind B** (enanas T1 + T6) | **Agua y metano detectados con claridad.** H2O-J = 0.34 ± 0.02 (46σ), H2O-H = 0.45 (10σ), H2O-K = 0.49 (17σ), CH4-K = 0.65 (12σ), **CH4 3.3 µm = 0.19 ± 0.01 (78σ)**, CH4-H = 0.86 (3σ, marginal). Se ven los picos J, H y K separados por bandas de agua y metano, y el gran pico a 4 µm típico de las enanas T (`docs/figures/spectrum_eps_ind_b.png`). Las ventanas "de hielo" no miden hielo en una enana marrón (lo indica `interpretation`) |
| **WISE 0855** | Solo D6 (4.4–5.0 µm) es utilizable; D1–D5 están mezclados con una estrella de fondo. CO 4.67: profundidad −0.01 ± 0.17, **sin restricción**. Con estos datos no se puede afirmar nada sobre sus moléculas |
| **M42 → BN/KL** | **Satura en D3–D6**: ~20 píxeles perdidos por exposición en 2.4–5 µm, así que todos los flujos ahí son cotas inferiores. **No se puede medir el hielo de 3.05 µm.** D1 está contaminado por la nebulosa; solo D2 es limpio. Queda en `public-data/custom/c2d9e7410cce7/analysis.json` con `target_px` dentro del campo M42 |
| **RW Aur** | Sin bandas significativas. El combinado mezcla pasadas de una estrella variable (lo indica `note`): usar los espectros por pasada |
| **R Dra** | 48 de 49 tramos son cotas inferiores (saturada): bandas no medibles |
| **Barnard** | Saturado por debajo de 4 µm: no sirve como control "sin metano" |
| **Candidata de hielo SPLICES J043136.14+181343.0** (flat-spectrum YSO, K = 9.7, a 37" de HL Tau) | **No satura** (174 de 179 exposiciones `ok`). Se ve el espectro creciente de una protoestrella con polvo caliente. **Hielo H₂O 3.05 µm: profundidad 0.11 ± 0.08 (1.3σ), no significativo.** CO₂ 4.27: sin datos en la ventana (con 10 exposiciones por grupo quedan huecos de longitud de onda). Queda en `public-data/custom/cd2f34edd4880/analysis.json` (campo de demo HL Tau) |

**Limitaciones:**
- Las fuentes muy brillantes en el infrarrojo saturan. Es una limitación de SPHEREx para las estrellas más brillantes del cielo.
- **Para medir hielo** hace falta una fuente de SPLICES que no sature y **más exposiciones**: con las ~380 disponibles (en vez de 10 por grupo) el S/N mejora ~2× y se llenan los huecos de longitud de onda. Eso son ~30 minutos de descarga por fuente.
- Los errores de los tramos con pocas exposiciones (1–2) son menos fiables.

## T4. Catálogo SPLICES

**Qué es** (página de IRSA y Ashby et al. 2023, doi:10.26131/IRSA554):
- La *SPHEREx Target List of Ice Sources*: ~8.9 millones de fuentes puntuales infrarrojas brillantes y aisladas, **en las que se espera** ver hielo cuando SPHEREx las observe.
- Versión servida: v8.6 (FITS de 3.1 GB).
- **No trae rasgos de hielo medidos.** Trae:
  - posiciones;
  - fotometría 2MASS, WISE, IRAC y Gaia;
  - clase de fuente (`class_1`: YSO_D/F/P) y clase por aprendizaje automático (`stype_ml`: Class I/II/III YSO, flat spectrum, AGB de carbono, MS…);
  - método de selección (`sel_type`), nombre propio, paralaje, movimiento propio y variabilidad NEOWISE.

**Acceso:**
- La tabla TAP `splices` existe, pero esa noche IRSA TAP devolvía 502 o se colgaba, incluso en búsquedas de cono a 2MASS.
- **IRSA Gator** (`/cgi-bin/Gator/nph-query?catalog=splices`) respondió en segundos, tanto en conos como en todo el cielo con filtros. Es lo que usa `analysis/splices.py`.

**Salida:** `public-data/catalogs/splices.json` (240 KB, 2 293 fuentes), en formato compacto `columns` + `rows`:
- **Regiones de 30'** alrededor de nuestros campos:

  | Campo | Fuentes |
  |---|---|
  | Barnard | 21 |
  | eps Ind B | 0 |
  | R Dra | 0 |
  | RW Aur | 62 |
  | WISE 0855 | 2 |
  | HL Tau | 150 |
  | Trapecio | 1 752 |
  | M42 | 1 748 |

  El Trapecio y M42 se solapan; las fuentes repetidas aparecen una sola vez, con varias regiones.
- **Todo el cielo:** 303 protoestrellas brillantes (`stype_ml` Class I o flat spectrum, K < 9).
- **`ice_priority`** es **nuestra heurística de visualización**, no un dato de SPLICES:
  - 1 = protoestrella embebida, donde se espera el hielo más fuerte (332 fuentes);
  - 2 = otra YSO (641);
  - 3 = el resto (1 320).

**Para el frontend (Aladin Lite):**
- Leer `columns` y `rows`, crear un `A.catalog` y agregar `A.source(ra, dec, {...})`.
- Colorear por `ice_priority` y filtrar por `regions` cuando se muestra un campo.
- Mostrar el aviso de `important`: son candidatas, no detecciones.
