# B2 fase 2: acceso real demostrado, curvas científicas pendientes

Estado comprobado el **15 de noviembre de 2026 (Europe/Paris)**, rama
`feature/b2-science`. No hay commits ni pushes. No se modificaron B1, B3,
`app/main.py`, rutas HTTP ni pruebas originales. No se declara completada la fase:
se ha demostrado adquisición y procesamiento de datos reales, pero no una curva
de brillo científicamente validada para ninguno de los dos objetivos.

## Archivos

Nuevos en `app/b2/`:

- `observation_models.py`: contratos aditivos Pydantic v2.
- `archive.py`: Astroquery/IRSA SIA2 y caché de recortes IBE.
- `photometry.py`: fotometría forzada de apertura en coordenadas celestes.
- `compatibility.py`: agrupación por respuesta/calibración atestada; no por detector.
- `validated_images.py`: diferencia estricta con máscaras, fondo e incertidumbres.
- `pipeline.py`: ejecución por objetivo, reproducción offline y exportación.
- `demo.py`: CLI explícita, sin operaciones de red al importar.

Se añaden `tests/test_b2_observations.py` y `tests/test_b2_real_integration.py`.
Se amplía `docs/B2.md` y se crea esta guía más `b2-phase2-evidence.json`, que
conserva respuestas reales y metadatos de adquisición. `pyproject.toml` incorpora
solo el extra **b2-real** (Astroquery y Matplotlib), necesario para acceso y PNG.
Las dependencias básicas y los servicios anteriores permanecen compatibles.
Los directorios locales `.b2-cache/` y `.b2-runs/` tienen su propio `.gitignore`;
FITS y resultados locales no se incorporan automáticamente a Git. No se alteró
el `.gitignore` general.

## Consultas y adquisición reales

Fuentes primarias consultadas:

- https://irsa.ipac.caltech.edu/Missions/spherex.html
- https://caltech-ipac.github.io/irsa-tutorials/spherex/
- https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/
- https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts/

Las coordenadas se resolvieron con `SkyCoord.from_name` / CDS Sesame (`RW Aur`,
`R Dra`); esta fuente de coordenadas se registra separadamente de las observaciones
NASA/IPAC. Para reproducibilidad estricta se pueden suministrar RA/Dec explícitas
y su referencia; el movimiento propio y la posición de componentes requieren revisión.

| Objetivo | RA ICRS (deg) | Dec ICRS (deg) | Consulta SIA2 |
|---|---:|---:|---|
| RW Aurigae | 76.95652603458 | 30.40143817389 | radio 1 arcsec, MAXREC=8, 8 registros DR1 |
| R Draconis | 248.16761083295 | 66.75497941722 | radio 1 arcsec, MAXREC=8, 8 registros DR1 |

Ambas consultas pidieron `spherex_dr1` y `spherex_qr3`. Los subconjuntos devueltos
fueron DR1 y alcanzaron el límite: **no demuestra que QR3 esté vacío**, ni que se
conozca toda la cobertura temporal. No se garantiza un orden temporal de SIA.
Hubo llamadas iniciales MAXREC=4 que llegaron al servicio pero fallaron en el
adaptador por asumir un retorno PyVO; se corrigió para aceptar `Table` directamente
(Astroquery 0.4.11) y también objetos con `to_table()`.

Internet falló por DNS en el sandbox. Las consultas y descargas posteriores se
ejecutaron con acceso permitido y sí tuvieron respuestas reales. Los fallos
iniciales se conservan en `.b2-runs/*/failure.json`, sin presentarlos como éxitos.
También pasó una consulta independiente de integración, MAXREC=2, en la posición
del tutorial oficial (304.693508808, 42.4436872991 grados).

Se solicitaron como máximo dos recortes por estrella, `size=0.03` grados;
4 MB por archivo, 16 MB por ejecución, 90 segundos de presupuesto de descarga.
Se guardaron **tres FITS, 11 856 960 bytes en total**:

| Objetivo | Observación | Detector | MJD-OBS / UTC | Bytes |
|---|---|---:|---:|---:|
| RW Aurigae | 2025W36_1A_0095_1 | 1 | 60919.419646597 | 3 954 240 |
| RW Aurigae | 2025W36_1A_0095_1 | 4 | 60919.419646609 | 3 951 360 |
| R Draconis | 2025W20_2D_0243_1 | 6 | 60811.955829144 | 3 951 360 |

Origen: `https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/...` con parámetros
oficiales `center` y `size`. URLs completas, SHA-256 y fecha de recuperación UTC
están en `b2-phase2-evidence.json`, los sidecars del caché y cada `run.json`.
El producto de RW Aur usa `VERSION=7.0.5`; la ruta conserva además la versión de
procesamiento `l2b-v27-2026-232`. No se sustituye una por otra.
Los recortes incluyen IMAGE, FLAGS, VARIANCE, ZODI, EPSF y WCS-WAVE; EPSF domina
su tamaño aun para imágenes de 18x18 píxeles. Un cuarto recorte de R Dra excedió
4 MB y se rechazó sin conservar un archivo parcial ni declararlo descargado.
Los reintentos pueden transferir bytes adicionales; el tamaño anterior describe
solo los archivos FITS completos conservados, no todo el tráfico HTTP.

## Fotometría y límites científicos

La primera implementación detectó que los píxeles reales no satisfacían una
aproximación de cuadrícula cuadrada. Se usa ahora apertura circular **en cielo**,
submuestreo 5x5, WCS con SIP para astrometría y áreas sólidas de cuadriláteros
esféricos por píxel. Los radios se expresan en píxeles equivalentes locales.
La longitud de onda y el ancho de banda se leen del WCS alternativo W con
WCS-WAVE y `spectral_wcs.sip=None`, según IRSA; no se supone un eje lineal.
No se ignora globalmente la información o las advertencias de Astropy.

Se usa IMAGE calibrada en MJy/sr, VARIANCE en unidades cuadradas compatibles,
FLAGS y fondo medio de un anillo local. No se resta además ZODI, pues el fondo
local ya trata su contribución constante; estructuras o gradientes requieren
inspección. No se aplican correcciones de apertura, PSF, color o contaminación.
Las áreas transforman brillo superficial a Jy. La varianza propaga pesos de
apertura y error del fondo (máximo entre varianza instrumental y dispersión del
anillo); presupone píxeles independientes y excluye sistemáticos de calibración.

Política de flags **conservadora**, explícita y registrada: rechazar todos los
bits salvo SOURCE(21) y FULLSAMPLE(12), máscara decimal **4292866047**. Referencia:
cabeceras FLAGS y sección 9 del tutorial oficial. SOURCE no se confunde con un
píxel malo. No se rellenan ni reescalan huecos en la apertura para forzar una medida.
La política necesita revisión científica por release antes de producción.

Reprocesación offline, apertura 2.5, anillo 5–7 píxeles equivalentes:

- **RW Aurigae D1:** una medida aceptada, MJD 60919.419646597 UTC,
  lambda aproximada 1.068315 um, ancho 0.028263 um. Flujo de apertura preliminar
  ~0.15227 Jy, incertidumbre estadística ~0.00084 Jy. No es flujo total corregido,
  ni medida separada de RW Aur A, ni demostración de variabilidad.
- **RW Aurigae D4 y R Draconis D6:** apertura con píxeles inválidos/rechazados;
  no se emite flujo. Con el anillo inicial de 8 píxeles también se encontró
  cobertura insuficiente para D4. Cambiar a 7 solo asegura cobertura del fondo;
  no elimina la exclusión por flags.
- **Curvas de brillo válidas: ninguna.** Solo una medida aceptada y ninguna
  respuesta espectral equivalente verificada entre épocas. No hay magnitudes:
  falta calibración de flujo total/apertura y cero fotométrico aplicable a la
  respuesta efectiva. No se descargó fotometría externa para ocultar esta falta.

`group_compatible_samples` exige `response_id` atestado externamente (incluyendo
calibración aplicable), misma colección, versión, detector, apertura, objetivo y
escala temporal; excluye muestras sin respuesta/época y duplicados. Solo agrupa
y ordena: no promedia ni certifica una curva. Igual detector o longitud de onda
redondeada no identifica una banda compatible en un instrumento LVF.

Resultados locales:

- `.b2-runs/rw-query-live-v2/search.json`, `rdra-query-live-v2/search.json`.
- `.b2-runs/rw-demo/run.json`, `measurements.csv`, `samples.png`.
- `.b2-runs/rdra-reprocessed/run.json`, `measurements.csv` (sin filas).
- `.b2-runs/*-photometry-live/` conserva la primera pasada y sus fallos.

El PNG muestra muestras aisladas etiquetadas por longitud de onda; **no es una
curva de brillo**. No se produce un PNG con puntos inventados para resultados vacíos.

## Ejecución y contratos para B3

```powershell
venv/Scripts/python.exe -m pip install -e ".[dev,b2-real]"
venv/Scripts/python.exe -m app.b2.demo --help
# Solo metadatos; elegir un directorio nuevo en cada ejecución.
venv/Scripts/python.exe -m app.b2.demo --target "RW Aurigae" --limit 8 --output .b2-runs/my-query
# Recortes acotados y fotometría; política conservadora revisable.
venv/Scripts/python.exe -m app.b2.demo --target "RW Aurigae" --limit 8 --max-files 2 --download --annulus-outer 7 --reject-bits 4292866047 --flag-policy-source "IRSA tutorial section 9; reject all bits except SOURCE and FULLSAMPLE" --output .b2-runs/my-live
# Repetir desde archivos ya obtenidos, sin red:
venv/Scripts/python.exe -m app.b2.demo --target "RW Aurigae" --reprocess .b2-runs/rw-demo/run.json --annulus-outer 7 --reject-bits 4292866047 --flag-policy-source "IRSA tutorial section 9; reject all bits except SOURCE and FULLSAMPLE" --output .b2-runs/my-offline
```

La caché usa hash de URL (incluidos centro y tamaño), checksum y verificación FITS.
No acepta redirecciones, hosts alternativos, enlaces simbólicos de entrada o
productos con IMAGE mayor de 128 píxeles por eje. Archivos y directorios de salida
existentes no se sobrescriben. Los límites son por instancia/ejecución; no existe
evicción ni cuota global automática, y ejecuciones sucesivas pueden acumular datos.
Mantener un directorio de caché confiable con política de almacenamiento del servidor.
La consulta usa timeout de conexión/lectura (10/30 s) en la sesión privada de
Astroquery, MAXREC<=100, radio<=0.1 grados y hasta tres intentos (dos por defecto).
La descarga usa dos intentos como máximo, no reintenta 404 ni FITS inválidos.
El presupuesto de tiempo se comprueba entre lecturas; una lectura HTTP puede
demorarse hasta su timeout. No hay garantía de tiempo real estricto.

Contratos Pydantic JSON/OpenAPI (sin endpoints nuevos):

| Contrato | Contenido |
|---|---|
| Target / ObservationQuery | Identidad, RA/Dec, origen de coordenadas, radio, colecciones, límite |
| ObservationSearch / Observation | Estado, consulta, truncamiento, URL, colección, MJD inicial/final, banda/detector |
| CachedCutout | FitsAsset relativo al cache_root, URL de recorte, fecha UTC, bytes, SHA-256 |
| ApertureConfig / Measurement | Política de flags, apertura, versión, época/escala, lambda/ancho, Jy/error, fondo, estado y advertencias |
| CompatibleSamples | Grupos de respuesta atestada, exclusiones y advertencias |
| ScienceRun / ProcessingIssue | Resultados parciales, fallos por etapa, procedencia y rutas relativas al output |
| FrameSpec / ValidatedDifference | Adaptador de diferencia con metadata opcional de objetivo/observación, unidades, errores y advertencias |

`Observation.time_scale` queda null si SIA no la declara. Measurement usa TIMESYS
y MJD-OBS de FITS (inicio de observación, no punto medio inventado). Las rutas de
entrada son relativas al cache_root y las de resultado al directorio de exportación.
La versión de datos de cada muestra se conserva, sin agrupar releases por defecto.
Los fallos de consulta no se interpretan como ausencia de observaciones. B3 debe
mapear errores HTTP, fijar directorios confiables y ejecutar I/O síncrona fuera
del event loop. Validar políticas y recursos antes de exponer estas funciones.

## Diferencias y coordinación con B1

La función anterior `difference_images` conserva su API de fase 1. Para datos
reales utilizar **validated_difference**: exige igualdad de detector, response_id,
calibration_id y psf_match_id, WCS celeste idéntico (incluyendo SIP), dimensiones
y unidades convertibles. Comprueba FLAGS, varianzas y máscaras independientes
de cielo vacío. Archivos auxiliares separados deben declarar el mismo WCS;
HDUs del mismo archivo se interpretan en la cuadrícula de IMAGE.
Se resta el offset medio en >=20 píxeles de cielo común. Si hay varianza en ambos
inputs, se propaga A+B y la varianza del offset; dentro de la región de estimación
se incluye el término de covarianza con esa media. Sin ambas varianzas el error
sale null y se advierte; no se inventa. No realiza registro, resampling ni ajuste
de PSF. Los identificadores son atestaciones del adaptador, no pruebas físicas.

La prueba preparada consume **salida de un adaptador B2**, no un manifest B1
inventado: un objeto con `science` y `reference`, cada uno validable como FrameSpec.
Cada asset indica path relativo, HDU y procedencia. La integración permanece
omitida hasta contar con archivos reales registrados y compatibles.

Se necesita de B1: schema/version de su manifest y adaptador acordado, URI/checksum,
colección/release y versión de procesamiento, HDUs explícitos IMAGE/FLAGS/VARIANCE,
definición de bits por release, WCS completo con SIP y WCS-WAVE, fechas y TIMESYS,
respuesta espectral efectiva por observación, calibración y corrección de apertura,
PSF/registro, máscara de cielo vacío y metadatos del objetivo/componente. No basta
con el número del detector para autorizar una resta o una curva.

## Pruebas

Se preservan las 25 originales. Se añaden FITS temporales explícitamente sintéticos
para comprobar cálculos, fondo, varianza, máscara, datos faltantes, unidades,
archivos corruptos, límites, caché, red, consultas vacías y contratos OpenAPI.

```powershell
venv/Scripts/python.exe -m pytest -q
venv/Scripts/python.exe -m mypy
venv/Scripts/python.exe -m compileall -q app/b2
venv/Scripts/python.exe -m pip check
# Integraciones reales explícitas; no descarga imágenes nuevas:
$env:B2_LIVE_IRSA = "1"
$env:B2_DATA_ROOT = (Resolve-Path .b2-cache).Path
$env:B2_REAL_ASSET_JSON = (Resolve-Path .b2-runs/real-asset.json).Path
$env:B2_REAL_RUN_JSON = (Resolve-Path .b2-runs/rw-demo/run.json).Path
venv/Scripts/python.exe -m pytest -q
# Para la pareja de B1, cuando exista:
# $env:B2_REAL_PAIR_JSON = "ruta/a/salida-adaptador-b2.json"
```

Verificación ejecutada en Python 3.14.7: **57 aprobadas, 1 omitida** habilitando
consulta SIA pequeña, lectura del FITS real y reproducción fotométrica real.
La omitida requiere la pareja B1. Mypy sin errores en 15 archivos, compileall,
pip check y diff check correctos. Se mantiene la advertencia de deprecación de
TestClient/Starlette por httpx, con pruebas HTTP aprobadas. Las integraciones
reales se omiten por defecto; los tests offline no se presentan como observaciones.

Preparación para demo: consulta real, procedencia, caché y una medida preliminar
reproducibles; curvas validadas, magnitudes y diferencias reales aún pendientes.
No se afirma ninguna detección molecular.
