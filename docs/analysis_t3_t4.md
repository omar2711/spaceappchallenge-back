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

**Limitaciones:**
- Las fuentes muy brillantes en el infrarrojo saturan. Es una limitación de SPHEREx para las estrellas más brillantes del cielo.
- **Para mostrar hielo de verdad conviene una fuente de SPLICES con brillo moderado** (ver T4).
- Los errores de los tramos con pocas exposiciones (1–2) son menos fiables.
