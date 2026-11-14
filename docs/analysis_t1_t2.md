# Análisis B2 — T1 (diferencias) y T2 (curvas de luz), 2026-11-14

Código en `analysis/`; uso y contrato en `analysis/README.md` y `analysis/analysis.schema.json`.

## T1. Imágenes de diferencia

- `k·B − A` sobre la grilla común de B1, después de restar la mediana recortada de cada imagen.
- `k` sale de estrellas del campo (S/N > 10, a más de 5 px del objetivo, sin núcleo rellenado). Con menos de 3 estrellas se usa k = 1 y se marca.
- El error del residuo es **empírico**: aperturas al azar sobre la misma diferencia. La varianza propagada subestima el ruido.

**Validación:**
- **Barnard:** el dipolo apunta en la dirección del movimiento en los 6 detectores. Ángulo de posición medido 334°–4° contra 355.6° esperado (D6).
- **WISE 0855:** en D6, S2→S3, 262° medido contra 275° esperado. S1→S2 es ruido (S1 tiene 1 día y pocas exposiciones).
- **eps Ind B:** el residuo es < 3 % y no significativo en D6, como se esperaba. En D1–D5 hay residuos de 2–50 %, que **siguen a la diferencia de longitud de onda media entre pasadas**. Ejemplo en D2: 1.286 → 1.371 µm da −18 %, y 1.371 → 1.335 µm da +17 %. Es el espectro de la enana T (pico J y banda de agua dentro del detector), no variabilidad. Por eso la diferencia **sirve para ver**, no para medir, y cada par lleva `caveats`.
- **A simple vista:** R Dra en D1 se ve azul (se apaga) y luego rojo (se enciende); RW Aur en D1, rojo (se abrillanta).

## T2. Curvas de luz

- **Fotometría de apertura** forzada en 1 441 exposiciones (r = 12", anillo de 31–49"). El fondo es igual al de B1 (ZODI + plano).
- **Flags:**
  - `saturated` si se perdió el núcleo (NaN); el flujo es una cota inferior.
  - `contaminated` si más del 20 % de la apertura está enmascarada o con GHOST/CROSSTALK/HALO.
  - `blended` en WISE 0855 D1–D5.
- **Corrección espectral:** `flujo = S(λ)·g(pasada)` por detector, con `S` por tramos. Un polinomio dejaba 36–49 % de dispersión en eps Ind B D2–D3; los tramos la bajan a 4–6 %.
- **Significancia:** χ² de las pasadas contra un valor constante, con un piso sistemático del 3 %; significativo si p < 0.001.
- **Detección:** S/N combinado ≥ 5 sobre todas las exposiciones del detector.

**Resultados:**

| Objetivo | Resultado |
|---|---|
| **eps Ind B (control)** | **Plana en los 6 detectores** (p = 0.45–0.95). Amplitud 0.028–0.034 mag en D3, D5 y D6 |
| **Barnard (control extra)** | Plana. D5: 0.005 mag; D6: 0.037 mag. D1–D4 saturados (cotas inferiores), sin variabilidad significativa |
| **WISE 0855** | Solo D6 utilizable: S/N combinado 19.5, **0.53–0.59 mJy**. Literatura: Spitzer [4.5] ≈ 0.50 mJy, W2 ≈ 0.43 mJy. Sin variabilidad (p = 0.96). D1–D5 mezclados con la fuente de fondo |
| **RW Aur** | **Variable, significativo** en D1 (+0.64 mag, se abrillanta), D2, D5 (−0.75 mag, se apaga) y D6 (−0.68 mag). Coincide con B1: más brillante en el visible y más débil en el infrarrojo térmico. Ninguna exposición pierde el núcleo |
| **R Dra** | **Variable, significativo** en D1 (1.19 mag), D5 y D6. 107 de 108 exposiciones saturadas: amplitudes basadas en cotas inferiores (`lower_limit`). El "~2.2 mag" que reportó B1 en D1 estaba inflado por el muestreo de longitud de onda (S2 solo vio 0.75–0.82 µm) |

**Limitaciones:**
- R Dra tiene solo 108 de 539 exposiciones en caché: la pasada completa de B1 quedó incompleta.
- No hay sub-pasadas útiles: R Dra tiene 6 exposiciones por grupo.
- Las estrellas saturadas (Barnard D1–D4, R Dra) solo dan cotas inferiores. La fotometría con las alas de la PSF podría recuperarlas; queda pendiente.
- Los errores de cada exposición vienen de VARIANCE; la dispersión real después de la corrección es de ~4–6 %, que es el dato honesto.
