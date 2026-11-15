# B2 fase 3 — ejecución real, límites científicos y demostración offline

Fecha: **15 de noviembre de 2026, Europe/Paris**. Rama: `feature/b2-science`.
No se cambió de rama, no hubo commits/pushes ni eliminación de archivos. B1, B3 y
los endpoints de `app/main.py` permanecen intactos. La fase **no está completada**:
hay consultas y FITS reales reproducibles, una estimación fotométrica de baja
significancia y una consulta SPLICES real; no se han obtenido cinco espectros
completos validados, curvas de brillo válidas ni diferencias temporales reales.

## 1. Resumen técnico y auditoría

Se leyeron B2.md, B2_PHASE2.md, módulos, contratos y pruebas antes de extender B2.
La verificación inicial reprodujo **57 aprobadas y 1 omitida**. Se reutilizaron:

| Función existente | Estado comprobado y uso en esta fase |
|---|---|
| SIA2 / CutoutCache | Funcionan con IRSA real; se reutilizan límites, checksum, timeout y caché |
| read_image / aperture_measurement | Lectura FITS y cálculo reproducibles; sigue faltando validación de flujo total |
| summarize_curve / process_spectrum | Cálculos unitarios disponibles; no equivalen a curvas o detecciones reales |
| group_compatible_samples | Excluye muestras sin respuesta atestada; no certifica PSF/calibración |
| validated_difference | Pruebas sintéticas correctas; no hay pareja B1 real lista |
| SPLICES fase 1 | Adaptador existente conservado; ahora se añade un snapshot con unidades y servicio real |

Se detectó una limitación científica de fase 2: la configuración histórica de
fondo no excluía SOURCE. Una medida de apertura puede ser reproducible y aun así
no constituir fotometría validada. Se añadió una opción de máscara de fondo
independiente; su valor por defecto conserva compatibilidad con la fase 2. La
nueva receta exige excluir SOURCE en el fondo y conserva errores explícitos si
no quedan al menos 20 píxeles. No se sustituyen esos errores por datos rellenados.

## 2. Archivos creados y modificados

Nuevos módulos:

- `app/b2/targets.py`: identidad SIMBAD/CDS, astrometría y propagación por época.
- `app/b2/spectral_products.py`: contratos espectrales, importación de tablas del
  servicio oficial, muestras de apertura, unidades, calidad y JSON/CSV/PNG.
- `app/b2/catalog_snapshot.py`: TAP/SCS, estado VO, unidades y snapshots SPLICES.
- `app/b2/difference_export.py`: diferencias verificadas a FITS/PNG/JSON.
- `app/b2/phase3.py`: adquisición acotada de cinco objetivos, diagnósticos y replay.

Modificados: `app/b2/observation_models.py` (opción aditiva de máscara de fondo),
`app/b2/photometry.py` (aplicación de esa máscara y explicación de flags/rechazos),
y `docs/B2.md` (enlace a este informe). No se reescribieron servicios válidos ni
contratos anteriores. No se añadieron dependencias en fase 3.

Pruebas nuevas: `tests/test_b2_phase3.py`, `tests/test_b2_phase3_real.py`.
Evidencia: `docs/b2-phase3-evidence.json`, con procedencia, inventario de los FITS,
resultados reales y SHA-256 de los módulos B2 usados. Los outputs viven bajo
`.b2-runs/`; los FITS de observaciones, bajo `.b2-cache/`. Estos directorios ya
excluyen sus contenidos de Git. El estado Git previo incluía trabajo sin commits
de fases 1/2; se conservó.

## 3. Pruebas y calidad

La suite final habilita los datos reales locales y consultas pequeñas explícitas.
Incluye las pruebas originales, unidades sintéticas, reapertura de los FITS reales
de fase 3, checksum y replay de caché sin red, reproducción de la fotometría,
consulta SIA2, consulta SCS y validación del snapshot SPLICES real.

Se comprueban además tablas espectrales FITS/VOTable con datos sintéticos,
incertidumbres inválidas, valores faltantes, unidades ausentes/incompatibles,
calibración no declarada, archivos corruptos, flags de 64 bits, HTTP 200 con error
VO, red fallida, ausencia de resultados, máscara de fondo, exportación de diferencias,
Pydantic/OpenAPI y un roundtrip FastAPI aislado. No se registró esa ruta de prueba
en la aplicación real.

Resultado final y versiones de validación: véase el registro de ejecución al pie
del informe. Mypy comprueba **20 módulos**; también se ejecutaron compileall,
pip check y git diff --check. Python disponible: 3.14.7. No se certifican versiones
de Python adicionales que no se hayan ejecutado.

Las tablas numéricas de las pruebas unitarias son **sintéticas**, aunque imiten
el esquema de salida oficial. El lector de espectros oficiales pasó esas pruebas;
**no fue validado contra una exportación espectral oficial real**, porque no se
obtuvo tal exportación en esta ejecución. La prueba de pareja real de B1 sigue
omitida: no hay inputs compatibles disponibles.

## 4. Consultas reales y resolución de objetivos

Fuentes primarias:

- https://irsa.ipac.caltech.edu/Missions/spherex.html
- https://caltech-ipac.github.io/irsa-tutorials/spherex/
- https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/
- https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html
- https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/spectra.html
- https://irsa.ipac.caltech.edu/docs/vo_scs.html
- https://simbad.cds.unistra.fr/ (aviso oficial de incidencia y espejo)

SIMBAD principal devolvió 404. Se consultó el espejo recomendado por CDS,
`https://simbad.cfa.harvard.edu/simbad/sim-tap/sync`, que respondió para los cinco
aliases fijos: GJ 699, eps Ind B, WISE J085510.83-071442.5, RW Aur y R Dra. El
aviso de CDS indica que ese espejo contiene datos ingeridos hasta 2026-10-14.
Se conservan identidad resuelta, coordenadas ICRS J2000, movimiento propio,
paralaje, velocidad radial cuando existe, referencias bibliográficas y consulta.
SIMBAD proporciona astrometría, **no observaciones SPHEREx**.

La consulta SIA2 se centró en una posición propagada a J2025.5 (época elegida para
búsqueda, no una observación inventada), radio 1 arcsec, colecciones
`spherex_dr1`/`spherex_qr3`, MAXREC=48. Las cinco consultas devolvieron 48 filas;
son páginas truncadas, sin orden temporal garantizado ni inventario completo.
No se concluye que QR3 carezca de cobertura porque los recortes seleccionados
sean DR1. Se priorizan detectores diferentes al elegir hasta dos recortes nuevos
por objetivo. No se eligen aperturas por el signo o tamaño de su flujo.

Para adquisición se usa una posición aproximada de la época ObsCore; para medir
se lee **MJD-OBS y TIMESYS del FITS** y se vuelve a propagar el movimiento propio.
No se atribuye una extracción en coordenadas J2000 fijas a una estrella de alto
movimiento propio. La paralaje del observador y movimiento orbital no están
modelados. Si falta movimiento propio, la propagación se rechaza. Si falta
velocidad radial, la aceleración de perspectiva no queda plenamente restringida.

El registro astrométrico inicial contenía una advertencia genérica sobre Epsilon
Indi B en todas las fichas; el generador actual la limita al objetivo correspondiente.
Los JSON originales se conservaron, incluida esa advertencia histórica; no cambia
los parámetros astrométricos ni convierte otros objetivos en Epsilon Indi B.

## 5. Espectros y medidas por objetivo

| Objetivo | Recortes examinados en ejecución principal | Resultado con la receta estricta |
|---|---:|---|
| Barnard's Star | 2 | Sin medida aceptada: TRANSIENT, OVERFLOW, SUR_ERROR y BLOOM en la apertura |
| Epsilon Indi B | 2 | Cero píxeles válidos de fondo al excluir SOURCE; sin espectro extraído |
| WISE 0855 | 2 | Una estimación de apertura D6; el otro recorte se rechaza por OUTLIER |
| RW Aurigae | 3, incluyendo los 2 de fase 2 | Fondo insuficiente o flags en apertura; otro intento de descarga recibió 503 tras reintentar |
| R Draconis | 3, incluyendo el de fase 2 | Rechazos por flags; aparecen OVERFLOW, SUR_ERROR, NONFUNC y BLOOM según recorte |

Se intentaron adicionalmente dos recortes de Epsilon Indi B de 0.05 grados para
medir el fondo en un anillo 10–13 píxeles equivalentes. También resultaron
insuficientes tras excluir SOURCE; no se relajó la máscara para obtener un flujo.
El diagnóstico queda en `.b2-runs/phase3-background/target-1/`.

**Espectros completos calibrados obtenidos: cero.** No se confundió una lista de
imágenes espectrales con un espectro 1-D ya extraído, ni una única medida con un
espectro completo. La herramienta oficial usa modelado de fuentes/PSF con Tractor;
no se presenta nuestro extractor de aperturas como una reproducción de ese pipeline.
No se lanzaron trabajos masivos del servicio oficial de espectrofotometría.

La estimación real reproducible de WISE 0855 es:

- Producto DR1 `2025W19_1B_0116_1D6`, versión FITS 7.0.5; URL completa en JSON.
- Inicio de exposición MJD **60800.700028461 UTC**.
- Longitud de onda aproximada **4.96739658 um**, leída del WCS espectral.
- Flujo de apertura **0.0003562776295 Jy**, error estadístico **0.0003079331053 Jy**.
- **S/N = 1.15699684**: no constituye una detección del objetivo, ni molecular.
- SHA-256: `4857e47d9274bd279f718a89b3b7f577e902a30c3d5059af5219299a65dd9f53`.

Es una estimación forzada de baja significancia en una posición propagada, sin
corrección de apertura/PSF/color ni sistemáticos de calibración. Es compatible
con ruido. No es flujo total validado ni evidencia de absorción. La variación
del flujo con aperturas 2, 2.5 y 3 píxeles se conserva como diagnóstico, no como
calibración independiente: esas aperturas tienen errores correlacionados.

El producto JSON/CSV/PNG tiene `method=preliminary_aperture`, muestra S/N,
fecha, ancho de banda, posición de medida, colección, versión, checksum, URL de
recorte y advertencias. En la figura H2O 3.05 um, CO2 4.27 um y CO 4.67 um son
**referencias, no detecciones**. No se interpolan los intervalos sin datos.

El lector `read_official_spectrum` admite tablas FITS/VOTable del servicio oficial
con columnas documentadas wavelength, lambda_width, flux, flux_err, mjd, det_id,
data_collection, lvf_id y flags. Exige unidades físicas, versión, calibración y
política de bits explícitas; conserva valores negativos y filas rechazadas con
motivo, sin rellenar incertidumbres. Separa importación de datos y procesamiento
HTTP. Su ejecución con productos oficiales reales queda pendiente.

## 6. Curvas de brillo y revisión de RW Aurigae

**Curvas temporales científicamente validadas generadas: cero.** No se convierten
flujos a magnitudes ni se añaden fechas sin observación. Los campos response_id
siguen sin una equivalencia espectral/calibración atestada. Un mismo detector no
define una banda comparable en SPHEREx LVF.

La medida histórica ~0.15227 Jy de RW Aurigae sigue reproducible con su receta
de fase 2, pero no supera la nueva condición de fondo libre de SOURCE en estos
recortes. Debe permanecer histórica/preliminar, **no validada**. Su diferencia
frente a otros flujos o frente a WISE no es una comparación temporal. RW Aur
puede estar mezclada; no se atribuye el flujo a su componente A. Epsilon Indi B
puede corresponder a Ba/Bb no resueltas, no a Epsilon Indi A.

Para cerrar las curvas faltan fotometría con tratamiento de campo/PSF apropiado,
calibración de flujo total o apertura consistente, respuesta efectiva equivalente
y más de una época distinta aceptada. No se afirma que el archivo carezca de
épocas: la selección fue deliberadamente acotada.

## 7. Diferencias entre pasadas

`export_difference` llama primero a `validated_difference`: exige dimensiones,
WCS y escala idénticos, detector, response_id, calibration_id y psf_match_id
compatibles, unidades convertibles, máscaras y cielo común válido. Propaga
varianza instrumental y del fondo cuando ambas imágenes la aportan; si no,
la incertidumbre sale null y se advierte. No alinea ni ajusta PSFs automáticamente.

Los IDs de registro/PSF son atestaciones del adaptador B1; no prueban por sí
solos que las fuentes residuales estén alineadas. El exportador conserva
`temporal_comparison_verified=false`. No se declara validación física de PSF
o cambio temporal basándose solo en cabeceras o IDs iguales.

Exporta `difference.fits` (WCS, BUNIT, VALID y, cuando existe, UNCERTAINTY),
`difference.png` y `difference.json` con checksums y procedencia. Los inputs
sintéticos se identifican en la cabecera `SYNTHET`, JSON y título del PNG.

**Diferencias temporales reales: ninguna; integración bloqueada a la espera de
B1.** Se mantuvo la prueba real omitida y se ejecutaron pruebas sintéticas. Hay
un ejemplo persistente exclusivamente sintético en
`.b2-runs/phase3-difference-SYNTHETIC/`, con inputs claramente identificados en
`.b2-runs/phase3-synthetic-inputs/`. No forma parte del resultado observacional.

## 8. SPLICES real

Las consultas TAP de geometría agotaron sus timeouts, incluso con menor radio,
sin ordenación global y con preselección numérica. Se conserva el adaptador TAP,
pero no se afirma que esos intentos produjeran resultados. La inspección del
esquema sí respondió. Se verificó una respuesta del servicio oficial alternativo
Gator y finalmente se implementó **SCS**, recomendado por IRSA para conos pequeños.

Consulta reproducible:

```text
https://irsa.ipac.caltech.edu/SCS?table=splices&RA=76.95652603458&DEC=30.40143817389&SR=0.01&format=votable
```

Resultado: **1 fuente**, `source_id="854236268010143747"`, designación
`J050749.54+302404.7`, RA 76.956410 deg, Dec 30.401409 deg, dentro del cono de
36 arcsec. No se la identifica automáticamente con un componente de RW Aur.
Se registran metadatos de **157 campos**, incluidas unidades y descripciones.
Ejemplos de fotometría de catálogo: J~8.378 mag, H~7.621 mag, K~7.020 mag;
no son medidas espectrales SPHEREx ni una curva temporal. Los identificadores
de 64 bits se conservan como strings para evitar pérdida de precisión en JavaScript.

SCS no ofrece MAXREC: se limita el radio a <=0.01 grados, la respuesta a 2 MB y
la salida a <=10 filas, con indicación de truncamiento si procede. El snapshot
observado tiene una fila y no está truncado. Los valores/sentinelas del proveedor
se conservan; los ceros de columnas auxiliares no se reinterpretan como detecciones.

JSON final: `.b2-runs/phase3-splices-final/splices.json`.
SPLICES es una lista de candidatas a presentar hielos, no de detecciones
confirmadas. Citar Ashby et al. (2023) y DOI **10.26131/IRSA554**.

## 9. Inventario y procedencia de artefactos

Se conservan **14 recortes FITS reales, 55 612 800 bytes** en `.b2-cache/`:
los tres de fase 2 y once nuevos (43 755 840 bytes adicionales). Dos recortes
nuevos más amplios repiten imágenes de origen de Epsilon Indi B: el número de
archivos de recorte no es un número de épocas independientes. Los FITS sintéticos
de diferencias viven en otro directorio y no se cuentan como observaciones.

Adquisición principal: hasta dos nuevos recortes/objetivo, máximo diez intentos
de archivo, 5 MB por archivo, 45 MB globales, presupuesto de 300 segundos.
Seguimiento de fondo: dos recortes, 10 MB y 90 segundos. Un HTTP 503 siguió fallando
tras el reintento y quedó registrado. No se descargaron imágenes completas de
2040x2040 ni se borró/evictó el caché. Los límites son por ejecución y no una cuota
global permanente; el tráfico de reintentos puede superar los bytes conservados.

| Ruta local | Contenido |
|---|---|
| `.b2-runs/phase3-demo-final/index.json` | Índice para B3 con rutas relativas y estado por objetivo |
| `phase3-demo-final/target-N/target-result.json` | Contrato completo, consultas, rechazos, astrometría y espectrofotometría |
| `phase3-demo-final/target-N/photometry/` | run.json, measurements.csv y PNG solo cuando hay medida |
| `phase3-demo-final/target-2/spectral-0/` | spectrum.json, spectrum.csv y spectrum.png; una muestra WISE preliminar |
| `phase3-demo-final/target-N/aperture-validation.json` | Diagnóstico de aperturas; vacío cuando no hay medidas aceptadas |
| `phase3-demo-final/target-N/compatibility.json` | Grupos/exclusiones sin inventar response_id |
| `.b2-runs/phase3-live/` | Primera adquisición real, sin sobrescribirla |
| `.b2-runs/phase3-background/target-1/` | Intento adicional de fondo de Epsilon Indi B, rechazado |
| `.b2-runs/phase3-splices-final/splices.json` | Snapshot real SPLICES y metadatos |
| `docs/b2-phase3-evidence.json` | Inventario, URLs, fechas, checksums, consultas y resultados verificables |

Los archivos CSV sin filas de datos indican ausencia de medidas
aceptadas, no flujo cero observado. No se generan PNG con puntos inventados.
Las filas CSV espectrales usan nombres con unidades explícitas; las celdas con
listas/objetos contienen JSON. Las rutas en SpectralProduct son relativas a su
directorio de producto; las de ScienceRun, a `photometry/`; input_path, a cache_root.

## 10. Limitaciones científicas

- Cero espectros completos oficiales descargados. El parser oficial solo está
  comprobado con fixtures sintéticas, no con una exportación del servicio real.
- La máscara SOURCE impide validar el fondo de varios recortes; incluso ampliar
  el anillo de Epsilon Indi B no produjo cielo suficiente. Se necesita modelado
  de campo/PSF o una estrategia de fondo verificada, no ignorar ese flag.
- La única muestra nueva aceptada tiene baja S/N y no demuestra una fuente.
- No hay correcciones de apertura, color, PSF, flujo total ni error de calibración.
- Errores estadísticos con píxeles independientes; no se modela covarianza completa.
- Las longitudes de onda del WCS son aproximadas; no se infiere identificación
  molecular ni profundidad óptica a partir de referencias dibujadas.
- La astrometría propagada no incluye paralaje del observador, órbitas binarias
  o recentering. La velocidad radial no está disponible para todos los objetivos.
- MAXREC y presupuesto impiden concluir cobertura completa o inexistencia de datos.
- El tiempo de lectura de red se acota por timeout; el presupuesto no es tiempo
  real estricto. Se conservan INFO de Astropy sobre SIP al crear el WCS alternativo;
  se desactiva SIP para el WCS espectral según IRSA, sin eliminar SIP astrométrico.

## 11. Dependencias de B1

Pendiente acordar su manifest real; no se fabricó ni impuso uno. Se necesita:

1. URI, release, versión de procesamiento, checksum y HDUs IMAGE/VARIANCE/FLAGS.
2. Tiempos y TIMESYS, WCS astrométrico y espectral completos, posiciones por época.
3. Definición/política de flags y una estimación de cielo o modelo de fondo revisado.
4. PSFs y correcciones de apertura, calibración de flujo total y respuesta efectiva.
5. Para restas: dos inputs alineados, unidades compatibles, mismo canal/respuesta,
   PSFs igualadas, máscaras independientes de cielo y evidencia de la alineación.

`FrameSpec` sigue siendo un adaptador **B2**, no el contrato definitivo de B1.

## 12. Contratos y métodos para B3

Todos los cálculos siguen fuera de FastAPI. No se añadieron endpoints.

| Entrada / salida | Método reutilizable |
|---|---|
| Target, Astrometry | `targets.resolve_target`, `targets.target_at_epoch` |
| ObservationQuery, ObservationSearch, CachedCutout | `archive.search_observations`, `CutoutCache.fetch` |
| ScienceRun, Measurement, ProcessingIssue | canalización existente y `phase3.acquire_target` |
| SpectralPoint, SpectralProduct | `read_official_spectrum`, `from_measurements`, `export_spectral_product` |
| CompatibleSamples, CurveSummary | `group_compatible_samples`, `summarize_curve` |
| FrameSpec, ValidatedDifference, DifferenceArtifacts | `validated_difference`, `export_difference` |
| CatalogQuery, SplicesSnapshot | `splices_snapshot` (TAP), `scs_splices_snapshot` (SCS) |
| TargetResult | `phase3.export_target`; agrega estado, limitaciones y productos |

`accepted` significa muestra que pasa las validaciones implementadas, **no una
detección**. `detection_claim="none"`, `method`, S/N y warnings deben llegar a la
interfaz. `usable_samples` no significa espectro completo ni fotometría validada.
Los errores de red se propagan o se registran como ProcessingIssue; nunca se
transforman en catálogo vacío. B3 debe distinguir estado failed, empty y partial,
fuentes astrométricas, observaciones y datos sintéticos. No debe presentar bandas
de referencia como composición detectada.

Usar un directorio de datos confiable del servidor y resolver solo rutas relativas
permitidas al servir artefactos. Ejecutar las funciones de I/O síncronas en thread
pool desde endpoints async; no devolver rutas arbitrarias del sistema de archivos.

## 13. Demostración offline exacta

Desde la raíz del repositorio, con dependencias de fases anteriores instaladas:

```powershell
# No instalar ni resolver nombres durante la demostración.
# Comprobar primero los resultados ya existentes:
Get-Content .b2-runs/phase3-demo-final/index.json
Get-Content .b2-runs/phase3-splices-final/splices.json

# Recalcular desde los FITS locales. Elegir un directorio NUEVO.
venv/Scripts/python.exe -m app.b2.phase3 --offline .b2-runs/phase3-demo-final --cache .b2-cache --output .b2-runs/jury-offline

# Resultado real para el frontend:
Get-Content .b2-runs/jury-offline/target-2/spectral-0/spectrum.json
```

Mostrar `spectrum.png` junto a su JSON y advertencia de baja S/N, los rechazos
de los otros cuatro objetivos y SPLICES como catálogo candidato. El modo offline
no crea clientes HTTP ni consulta astrometría/archivo. Se ejecutó con éxito tanto
dentro del sandbox sin red como en pruebas que prohíben llamadas de descubrimiento.
Reutiliza y verifica los checksums; no escribe sobre los outputs anteriores.

Para trasladar la demo a otra máquina se necesitan el código B2 y dependencias
existentes, `.b2-cache/*.fits` más sus sidecars y el directorio de resultados.
Los caches/outputs están ignorados por Git: no se asumirán presentes después de
un clone. Copiarlos explícitamente junto con el inventario de checksums. El modo
offline de SPLICES es leer/validar el snapshot JSON; no repetir una consulta.

Para una adquisición futura acotada (requiere red, no es el modo de jurado):

```powershell
venv/Scripts/python.exe -m app.b2.phase3 --output .b2-runs/my-new-acquisition --cache .b2-cache --reuse .b2-runs/rw-demo/run.json --reuse .b2-runs/rdra-reprocessed/run.json
```

Pruebas con inputs reales explícitos:

```powershell
$env:B2_DATA_ROOT = (Resolve-Path .b2-cache).Path
$env:B2_REAL_ASSET_JSON = (Resolve-Path .b2-runs/real-asset.json).Path
$env:B2_REAL_RUN_JSON = (Resolve-Path .b2-runs/rw-demo/run.json).Path
$env:B2_PHASE3_BUNDLE = (Resolve-Path .b2-runs/phase3-demo-final).Path
$env:B2_REAL_SPLICES_JSON = (Resolve-Path .b2-runs/phase3-splices-final/splices.json).Path
# Añadir estas dos variables solo para pruebas de servicios externos:
$env:B2_LIVE_IRSA = "1"
$env:B2_LIVE_SPLICES = "1"
venv/Scripts/python.exe -m pytest -q --tb=short
venv/Scripts/python.exe -m mypy
venv/Scripts/python.exe -m compileall -q app
venv/Scripts/python.exe -m pip check
```

Sin flags externos las integraciones de servicios se omiten. La prueba B1 real
requiere además `B2_REAL_PAIR_JSON`; permanece omitida hasta disponer de esa pareja.

## 14. Siguientes acciones

1. Obtener exportaciones del servicio oficial de espectrofotometría para los
   cinco objetivos, con posiciones apropiadas y vecinos mezclados modelados.
   Importarlas con unidades, flags y calibración verificables; contrastar el
   lector contra al menos una tabla oficial real antes de declararlo validado.
2. Revisar el fondo SOURCE, saturación y PSFs con B1. No bajar las restricciones
   solo para aumentar la cantidad de puntos o fabricar una curva.
3. Seleccionar observaciones aceptadas de respuesta compatible y épocas distintas,
   resolver corrección de apertura y errores sistemáticos y entonces generar curvas.
4. Ejecutar la integración de diferencias sobre una pareja B1 real y revisar
   empíricamente registro/PSF antes de atribuir cambios temporales.
5. B3 puede integrar ya consultas, estados, procedencia y visualización de muestras
   preliminares. Debe mantener visibles las limitaciones descritas aquí.

La demostración actual muestra datos y cálculos reales con sus rechazos. No es
una demostración de detecciones ni de cinco espectros/curvas terminados.

## Registro final de verificación

- **Pytest: 86 aprobadas, 1 omitida, 2 advertencias**, con los datos y flags
  reales indicados en la sección 13. Incluye 79 pruebas unitarias con fixtures
  sintéticas/contratos y 7 integraciones reales (5 de archivos/resultados locales,
  2 de servicios externos). La omitida es la pareja real de B1.
- Se conservan todas las pruebas anteriores; las nuevas no sustituyen ni eliminan
  ninguna. Un fallo inicial en la fixture de límite SCS se corrigió antes de la
  ejecución final; no se convirtió un error de red en una respuesta vacía.
- Mypy: **sin errores en 20 archivos**. Compileall: correcto. Pip check:
  **No broken requirements found**. Git diff --check: correcto.
- Advertencias: deprecación TestClient/Starlette por httpx y una advertencia ERFA
  en la prueba **sintética** de movimiento propio sin distancia. No se ocultaron
  advertencias para aparentar validación científica.
- Replay offline completo de cinco objetivos ejecutado sin acceso de red.
- PNG espectral real inspeccionado visualmente; bandas marcadas como referencias,
  una única muestra con error, sin curvas interpoladas ni detecciones afirmadas.
- Exportación sintética de diferencias verificada con reapertura FITS y checksum;
  los artefactos persistentes indican explícitamente su carácter sintético.
- Rama final `feature/b2-science`; `app/main.py` sin cambios; sin commits/pushes.
