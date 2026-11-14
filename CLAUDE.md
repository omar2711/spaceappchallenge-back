# CLAUDE.md — Ruta del Agua

Proyecto del NASA Space Apps Challenge 2026 (sede Cochabamba). Tema y stack definidos (ver abajo).
Los acuerdos del equipo se registran en [docs/decisiones.md](docs/decisiones.md).

## Objetivo

Herramienta web pública que muestra el cielo de SPHEREx como video para ver qué se mueve o cambia de brillo, muestra de qué están hechos los objetos (espectros con bandas de agua) y sigue el rastro del agua hasta la Luna y Marte.

- 🔭 **Cielo** (principal): coordenadas → video del recorte, comparación entre fechas, flechas de movimiento de Gaia, espectro con agua. Debe funcionar con los 5 objetivos oficiales.
- 💧 **Agua**: capa del catálogo oficial de hielo y el cometa 3I/ATLAS.
- 🌙 **Luna**: sitios del polo sur según iluminación solar y visibilidad de la Tierra, más los sitios Apollo.
- 🔴 **Marte**: caminata planificada por zonas donde hubo agua.
- 📍 **Local**: visibilidad desde Cochabamba esta noche.

## Stack

| Capa | Herramientas |
|---|---|
| Datos (Python 3.11) | astroquery (IRSA: `spherex_dr1`, `spherex_qr3`; `astroquery.gaia` para Gaia DR3), servicio de recortes de IRSA, astropy, numpy, photutils, Skyfield (o JPL Horizons) |
| Backend | FastAPI, solo para cálculos en vivo |
| Frontend | React + Vite + TypeScript, Aladin Lite (HiPS de SPHEREx + capas Gaia/hielo), Canvas propio, Plotly, Leaflet + mosaicos Moon Trek / Mars Trek |
| Despliegue | Frontend: Vercel o GitHub Pages (enlace público obligatorio). Backend: Render o Railway gratis, solo si hace falta |

Recursos: tutoriales en https://caltech-ipac.github.io/irsa-tutorials/spherex y datos en https://irsa.ipac.caltech.edu/Missions/spherex.html

## Reglas críticas

- ⚠️ **Regla de oro de SPHEREx:** cada imagen es de una longitud de onda ("color") distinta. Para el video hay que **agrupar por pasada y por detector (1 a 6)** y comparar siempre **el mismo detector** entre fechas.
- Bajar solo **recortes** con el servicio de IRSA, nunca imágenes completas.
- Todo lo de la demo va **precalculado** (WebP + JSON). El backend se usa solo para lo que es imposible precalcular.
- Los FITS y datos crudos no se versionan (ver `.gitignore`). Solo se suben los productos finales livianos que usa el frontend.

## Estructura

```
pipeline/      Python (B1): descarga SPHEREx, suma por pasada×detector, export WebP + manifest. Ver pipeline/README.md
public-data/   Salida versionada del pipeline para la web: targets/index.json, targets/<id>/manifest.json + *.webp
analysis/      (B2) diferencias, curvas de luz, espectros — consume data/processed/<id>/*.fits
api/           (B3) FastAPI — sirve public-data/ y cálculos en vivo
docs/          decisiones, estado del pipeline (docs/pipeline_estado.md), guion y entrega
data/          NO versionado: raw/ (recortes IRSA), processed/ (FITS sumados), checks/ (imágenes de control)
```

Contrato pipeline → web: `pipeline/manifest.schema.json`. Comparar siempre el mismo detector entre pasadas.

## Convenciones

- Ver [CONTRIBUTING.md](CONTRIBUTING.md): ramas por persona/módulo, commits pequeños, merge a `main` cada 2–3 horas, nunca subir claves.
- _Pendiente: formato del JSON que intercambian el pipeline y el frontend._

## Módulos por persona

| # | Módulo | Responsabilidad | Persona | Rama |
|---|--------|-----------------|---------|------|
| 1 | Datos SPHEREx (crítico) | Bajar recortes de los 5 objetivos, agrupar por pasada y detector, sumar y generar los fotogramas del video | | |
| 2 | Comparación y espectros | Resta entre fechas, curvas de brillo de variables, espectros con bandas de agua marcadas | | |
| 3 | Backend y motor de posiciones | API, datos de Gaia, cálculos para Cochabamba y la Luna (Sol y Tierra) | | |
| 4 | Frontend del cielo | Visor Aladin Lite, video, controles, coordenadas en la URL, capas Gaia y hielo | | |
| 5 | Frontend Luna y Marte | Sitios lunares con línea de tiempo, sitios Apollo, mapa de la caminata en Marte | | |
| 6 | Historia y entrega | Guion, video, diapositivas, página en Space Apps, ensayos | | |
