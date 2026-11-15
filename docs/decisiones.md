# Decisiones del equipo

Registro de acuerdos del equipo. Agrega las nuevas decisiones arriba.

## Plantilla

### AAAA-MM-DD HH:MM — Título de la decisión

- **Contexto:** ¿qué problema o pregunta había?
- **Decisión:** ¿qué se acordó?
- **Responsables:** ¿quién lo lleva a cabo?

---

## Decisiones

### 2026-11-14 23:00 — No integrar `feature/b2-science`

- **Contexto:** FlavioC30 subió `feature/b2-science` (módulo `app/b2/`) en paralelo al backend de `main`.
- **Decisión:** no se integra a `main`. Queda en el remoto sin mezclar y sin borrar.
- **Responsables:** Renny (B1/B2/B3 en `main`).

### 2026-11-14 — Tema, stack y reparto

- **Contexto:** el repositorio se creó sin tema ni stack definidos.
- **Decisión:** el proyecto es **Ruta del Agua** (cielo SPHEREx → agua → Luna → Marte → Cochabamba). Stack: Python 3.11 para datos (astroquery, astropy, photutils, Skyfield), FastAPI solo para cálculos en vivo, React + Vite + TypeScript con Aladin Lite, Plotly y Leaflet. La demo va precalculada en WebP + JSON. Frontend en Vercel o GitHub Pages.
- **Reparto:** 6 módulos (datos SPHEREx, comparación y espectros, backend, frontend del cielo, frontend Luna y Marte, historia y entrega). Personas por asignar.
- **Regla de oro:** agrupar por pasada y detector (1–6) y comparar siempre el mismo detector entre fechas.
