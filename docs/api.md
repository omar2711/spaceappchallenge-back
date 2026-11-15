# Contrato de la API

La API FastAPI vive en `app/main.py` y usa `/api/v1` para los recursos que consume
el frontend. Los productos públicos se sirven desde `public-data/`; los datos crudos
de `data/` nunca forman parte de una respuesta pública.

## Productos SPHEREx

| Método | Ruta | Fuente |
|---|---|---|
| `GET` | `/api/v1/targets` | `public-data/targets/index.json` |
| `GET` | `/api/v1/targets/{target_id}` | Manifest validado contra `pipeline/manifest.schema.json` |
| `GET` | `/api/v1/targets/{target_id}/analysis` | `public-data/targets/{target_id}/analysis.json` |
| `GET` | `/data/targets/...` | WebP y JSON publicados |

El frontend debe recorrer los frames de un mismo detector. No debe mezclar D1–D6
en un único video porque cada detector cubre una banda distinta.

## Coordenadas personalizadas

```text
POST /api/v1/custom
GET  /api/v1/custom/{job_id}
GET  /api/v1/custom/presets
```

El `POST` recibe `ra`, `dec`, `fov_arcmin` y `max_exposures_per_group`. Devuelve
`202` cuando el trabajo está encolado o procesando y `200` cuando el resultado ya
está en caché. Los valores inválidos devuelven `422`; un `job_id` inexistente
devuelve `404`.

Los límites son RA `[0, 360)`, Dec `[-90, 90]`, FOV `(0, 6]` y entre 1 y 30
exposiciones por grupo. El valor recomendado para la demo es 2.

## Astronomía local y Luna

```text
GET /api/v1/visibility/cochabamba/{target_id}?at=2026-11-15T04:00:00Z
GET /api/v1/moon/sites
GET /api/v1/moon/sites/{site_id}/conditions?at=...
```

Las fechas se interpretan en UTC. La visibilidad de Cochabamba exige noche
astronómica y una altura mínima de 20 grados. Las condiciones lunares usan un
modelo aproximado de marco fijo lunar y lo declaran en la respuesta.

## Agua, Marte y 3I/ATLAS

```text
GET /api/v1/mars/route
GET /api/v1/ice
GET /api/v1/comets/3i-atlas
```

Estos recursos se almacenan como JSON versionado:

- `public-data/mars/route.json`
- `public-data/ice/catalog.json`
- `public-data/comets/3i-atlas.json`

El catálogo de hielo es un subconjunto de demo. La ficha de 3I/ATLAS no entrega
una posición si no existe una efeméride autorizada; debe integrarse JPL/Horizons
antes de mostrar coordenadas dinámicas.

## Salud y configuración

```text
GET /health
GET /health/ready
```

`/health/ready` verifica que los artefactos mínimos estén presentes. CORS se
configura con `API_CORS_ORIGINS`, separado por comas. El despliegue de Render
usa `render.yaml`.
