# Pipeline — Fase 5: los 5 objetivos (2026-11-14)

```
.venv/Scripts/python -m pipeline.build --all --max-per-group 6   # rápido: 6 exposiciones por pasada × detector
.venv/Scripts/python -m pipeline.build --all                     # completo
.venv/Scripts/python -m pipeline.report                          # validación por objetivo
```

## Configuración

- `pipeline/targets.yaml` guarda la astrometría de cada objetivo, así las corridas no dependen de SIMBAD ni de Gaia.
  - Barnard: Gaia DR3, época 2016.0.
  - El resto: SIMBAD vía CDS Sesame, época J2000. SIMBAD TAP devolvía 404 todo el día.
- **WISE 0855:** la posición de SIMBAD, llevada hacia atrás con su movimiento propio, coincide con la del enunciado en la época 2010.4 (la de WISE).

## Resultados (pasada rápida, 6 exposiciones por grupo)

| Objetivo | Pasadas | Frames | Validación |
|---|---|---|---|
| Barnard | 3 (ago 2025 – sep 2026) | 18 | Movimiento S1→S3 de 10.4" (Gaia: 10.3"). Error mediano 0.95", máximo 1.5" (18 pares) |
| Epsilon Indi B | 4 (abr 2025 – oct 2026) | 22 | Movimiento S1→S4 de ~6.5" (esperado 6.7"). Error mediano 1.0". Muy débil en D1 (es una enana T). Faltan D1 y D4 en S4 |
| WISE 0855 | 3 (may 2025 – may 2026) | 18 | **Se detecta en D6 por su movimiento**: el centroide se mueve 7.2" entre S1 y S3 (esperado 8.0"). En D1–D3 hay una fuente de fondo fija en la misma posición (se mueve 0.0–0.3"); D5 es una mezcla (5.5"). Con la pasada completa: 93 exposiciones D5+D6 |
| RW Aur | 3 (sep 2025 – sep 2026) | 18 | Variable: D1 ×2.3 más brillante y D5–D6 ÷2 entre S1 y S3. Saturada |
| R Dra | 3 (may 2025 – jul 2026) | 18 | Variable tipo Mira: D1 baja 7.6 veces en S2 (~2.2 mag) y se recupera en S3. Muy saturada |

## Cambios al pipeline durante esta fase

- **Fondo:** plano ajustado por exposición, ignorando las estrellas. Antes era una mediana constante. Elimina gradientes de luz dispersa, como el que deja eps Ind A.
- **Escala WebP por detector:** mediana de los percentiles de cada frame. Así un frame malo (pocas exposiciones) no deslava los demás.
- **Núcleos saturados:** se rellenan con el máximo de los vecinos, de afuera hacia adentro, en lugar de un promedio. El promedio dejaba una "dona" oscura en R Dra, que tiene huecos de hasta 14 px. Siguen marcados en `FILLED`.

## Advertencias para B2

- **RW Aur y R Dra están saturadas:** los flujos en apertura son cotas inferiores.
- **Cada pasada muestrea longitudes de onda distintas dentro del detector.** Con pocas exposiciones, parte de la "variabilidad" puede venir de la pendiente del espectro. Para curvas de luz rigurosas hay que comparar exposiciones a la misma longitud de onda (tabla `EXPOSURES`).
- **R Dra:** cada pasada dura entre 67 y 88 días (está cerca del polo de la eclíptica), y la estrella cambia dentro de una misma pasada. Propuesta pendiente: dividir las pasadas en sub-pasadas de ~30 días para las variables.
