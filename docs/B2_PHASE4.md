# B2 fase 4 — integración y demostración verificable

Fecha: **15/11/2026 (Europe/Paris)**. Rama `feature/b2-science`.
Preparación: **lista para integración técnica/offline**, sin declarar terminados
los análisis científicos pendientes. No se modificaron B1, B3 ni endpoints; no
hubo commits/pushes, cambio de rama, borrado de funcionalidades o datos ni nuevas
descargas de observaciones.

## 1. Arquitectura final

Se auditó la documentación de fases anteriores, los 20 módulos B2 y las pruebas,
el índice fase3-demo-final y sus referencias/contratos. La base reprodujo 86 pruebas
aprobadas y una omitida antes de las extensiones.

La estructura existente se mantiene:

- Adquisición: archive, catalog/catalog_snapshot y targets; no se invocan desde
  la demostración ni desde los getters offline.
- Ciencia: photometry, lightcurves, spectra/spectral_products, compatibility,
  images/validated_images y preparación del cometa.
- Reproducción/exportación existentes: pipeline, phase3, difference_export.
- Integración nueva: `ScienceService` para B3, paquete/inventario en
  `offline_bundle`, rutas en `safe_paths`, comparación espacial en `spatial_wcs`,
  adaptador `B1Frame` y CLI `offline_demo`.

Los cálculos se reutilizan. Los modelos científicos siguen siendo TargetResult,
Measurement, Observation, SpectralProduct, SplicesSnapshot y DifferenceArtifacts.
Los nuevos modelos describen inventario, integridad y disponibilidad, no fórmulas
duplicadas. FastAPI sigue a cargo de B3. Dependencias comprobadas y ya declaradas
en pyproject.toml; esta fase no añade ninguna dependencia.

## 2. Archivos creados y modificados

Nuevos:

- `app/b2/safe_paths.py`: rutas relativas portables y resolución bajo roots confiables.
- `app/b2/offline_bundle.py`: manifest, selección explícita, checksums y exportación.
- `app/b2/service.py`: fachada tipada de lectura, estados y reproducción.
- `app/b2/b1_adapter.py`: datos requeridos de B1 y validaciones previas a diferencias.
- `app/b2/spatial_wcs.py`: igualdad de cuadrícula celeste/SIP sin confundir épocas.
- `app/b2/offline_demo.py`: empaquetado, validación y demo sin conexiones externas.
- `tests/test_b2_phase4.py`, `tests/test_b2_phase4_real.py`, `tests/conftest.py`.
- Esta guía, `docs/B2_HANDOFF.md` y evidencia `docs/b2-phase4-evidence.json`.

Modificados:

- `observation_models.py`: FrameSpec recibe desviación estándar opcional y campos
  de revisión/pasada/época, conservando los anteriores. Rechaza varianza y sigma
  simultáneas. B1Frame exige los metadatos adicionales sin duplicar FrameSpec.
- `validated_images.py`: utiliza el comparador espacial compartido y convierte
  sigma a varianza sin escribir en los originales.
- `images.py`: utiliza el mismo comparador espacial; conserva su API.
- `difference_export.py`: conserva checksums de sigma y marca como sintéticos
  los resultados que utilicen cualquier asset sintético, incluidas máscaras/ruido.
- `phase3.py`: entrada pública reprocess_target que reutiliza el cálculo existente.
- `docs/B2.md`: enlace al estado actual.

Los archivos y modificaciones anteriores sin commits se conservaron. El M de
pyproject.toml ya existía antes de esta fase; no se añadió dependencia en fase 4.

## 3. Resultados científicos disponibles

| Objetivo | Estado científico actual |
|---|---|
| Barnard's Star | Metadatos/FITS disponibles; fotometría rechazada por flags |
| Epsilon Indi B | Metadatos/FITS disponibles; fondo insuficiente al excluir SOURCE |
| WISE 0855 | Una estimación de apertura preliminar, S/N~1.16, sin detección |
| RW Aurigae | Fondo SOURCE inválido o flags en apertura; histórico no validado |
| R Draconis | Recortes con flags; ninguna secuencia comparable aceptada |

La integridad del almacenamiento es independiente del estado del análisis. Un
objetivo puede tener `processing_status=failed` y metadatos disponibles. La
fachada lo expresa mediante estados por funcionalidad para evitar que B3 oculte
los datos reales o declare confirmaciones que no existen.

WISE conserva flujo **0.0003562776294805186 Jy**, incertidumbre estadística
**0.00030793310530469154 Jy**, lambda aproximada **4.96739658 um**, MJD
**60800.700028461 UTC**, detector 6 y procedencia/checksum. S/N~1.16 es compatible
con ruido; la muestra no demuestra fuente ni molécula detectada. Las medidas de
apertura no incluyen correcciones de flujo total/PSF/color ni sistemáticos.

## 4. Datos utilizados y paquete

Se reutilizan los 14 FITS auténticos ya conservados, **55 612 800 bytes**. El
paquete requiere solo 12 recortes, **47 684 160 bytes lógicos**, enlazados al mismo
almacenamiento del caché. Los otros dos son intentos adicionales de fondo de
Epsilon Indi B y permanecen intactos, fuera del paquete de demo.

Directorio preparado: `.b2-runs/phase4-demo/`.

- 48 archivos inventariados: 12 FITS y 36 productos JSON/CSV/PNG, incluidos índice
  y SPLICES. Además está manifest.json, que no se incluye en su propio checksum.
- 450 149 bytes de productos, más el manifest; los bytes FITS no se duplicaron.
- Los 12 enlaces se comprobaron con samefile; sus checksums coinciden con el caché.
- El resumen final B3 está en `.b2-runs/phase4-final-summary.json`.
- La reproducción está en `.b2-runs/phase4-final-replay/`; no copia los FITS.

La exportación copia solo las referencias aprobadas del índice/contratos; no usa
un glob para incorporar todo el caché ni arrastra diferencias sintéticas. Incluye
el snapshot real SPLICES antes separado, con una fuente candidata y 157 campos
documentados. Su DOI es 10.26131/IRSA554; no son detecciones de hielo ni datos
espectrales SPHEREx. No se ejecutaron nuevas consultas de adquisición: solo las
dos pruebas pequeñas ya existentes de servicios SIA y SCS, separadas de la demo.

Se verifican rutas relativas, estructura, identidades, estado y número de puntos,
igualdad entre JSON embebido y exportado, procedencia y S/N consistente, WCS y
unidades de FITS, coordenadas/unidades de SPLICES y tamaño/SHA-256 de cada recurso.
Los URI https de origen son válidos; no se confunden con rutas de Windows.

El modo `link` requiere el mismo volumen y permisos para crear hardlinks. En el
sandbox se denegó inicialmente os.link; el paquete final se construyó fuera del
sandbox con acceso autorizado. El intento parcial `.b2-runs/phase4-package/` se
conserva, no es el paquete válido y no debe usarse. No se copió el caché como
solución silenciosa. El modo alternativo `external` exige un data_root explícito;
sin él falla la validación y no es autónomo.

## 5. Limitaciones pendientes

- Validar archivos no confirma calibración, fuente, molécula ni variabilidad.
- No hay flujo total/apertura corregida ni respuesta espectral equivalente atestada.
- La máscara de fondo SOURCE sigue dejando cero píxeles aceptados en varios casos.
- La adquisición previa fue acotada; no prueba ausencia de datos adicionales en IRSA.
- El lector de espectros oficiales sigue probado con fixtures sintéticas, no con
  una exportación real del servicio de espectrofotometría.
- Las posiciones propagadas excluyen paralaje del observador y órbitas binarias.
- Los IDs/evidencias de registro y PSF son atestaciones, no una validación empírica
  automática. Una diferencia calculada no demuestra cambio temporal.
- Los enlaces duros comparten los bytes originales: el paquete/caché debe servirse
  en modo de solo lectura. Cambiar cualquiera de ellos rompe los checksums.

Se conserva una advertencia genérica heredada sobre Epsilon Indi B en algunas
fichas antiguas. Está identificada en fase 3 y no cambia la identidad de otros
objetivos; las coordenadas/identificadores y evidencias originales no se reescriben.

## 6. Curvas de brillo y revisión fotométrica

Se recalcularon los cinco objetivos desde los FITS existentes y se compararon
las medidas aceptadas, sus errores y longitudes de onda con la ejecución anterior.
La estimación de WISE se reproduce sin reclasificarla. RW Aur sigue rechazada con
el fondo SOURCE; no se relajó la máscara ni se usó ese fondo como cielo limpio.
Su valor histórico ~0.15227 Jy queda no validado y no se ofrece como punto aceptado.

En R Draconis, los tres recortes examinados tienen píxeles rechazados y no aportan
una secuencia aceptada de la misma respuesta calibrada. No se rellenan fechas,
flujos ni errores. **Curvas validadas: cero.** No se generan magnitudes sin una
calibración fotométrica apropiada ni se conecta una muestra aislada como curva.

## 7. Espectros y disponibilidad

Las consultas y el caché de los cinco objetivos se reutilizan, sin extracción
experimental ni descargas masivas. La única muestra espectrofotométrica aceptada
se mantiene como `preliminary_aperture`; el servicio la presenta como `incomplete`.
Los demás tienen `unavailable`, con los rechazos conservados en TargetResult.

**Espectros completos validados: cero.** JSON/CSV/PNG de la muestra WISE existen
en `target-2/spectral-0/`; no se generan productos ficticios para los otros cuatro.
H2O 3.05 um, CO2 4.27 um y CO 4.67 um son marcadores de referencia, no detecciones.

## 8. Diferencias temporales

**Diferencias reales registradas: cero**. ScienceService devuelve una lista vacía
y estado blocked; no inserta la demostración sintética de fase 3 como observación.
Se mantienen ambas pruebas reales de diferencias omitidas hasta que B1 entregue
inputs válidos: la interfaz histórica FrameSpec y el adaptador estricto B1Frame.

Se detectó/corrigió un defecto: Astropy puede conservar MJD-OBS y otras tarjetas
temporales incluso en to_header de un WCS celeste. Compararlas literalmente
rechazaba cuadrículas iguales tomadas en épocas distintas. same_celestial_grid
compara el transformado espacial 2D y SIP, excluyendo metadatos temporales y de
posición del observador. Las épocas se verifican por separado en el adaptador.
Una prueba asegura que cambiar un coeficiente SIP sí impide la equivalencia.
No se consideran equivalentes imágenes solo por tener las mismas dimensiones.

## 9. Integración B1

B1Frame es una **entrada del adaptador B2**, no un manifest definitivo impuesto a
B1. Extiende FrameSpec: objetivo/coordenadas, época/escala, pasada y banda efectiva,
assets de imagen/flags/cielo y varianza o sigma, detector, calibración/respuesta,
PSF y evidencias de revisión, procedencia y WCS/unidades declaradas opcionales.

Se exigen rutas seguras al root del servidor, MJD-OBS/TIMESYS coherentes en el
HDU seleccionado, pasadas y épocas distintas, mismo objetivo/banda efectiva,
geometría celeste/SIP compatible, unidades convertibles, ruido en unidades
correctas, máscaras válidas y compatibilidad de detector/respuesta/calibración/PSF.
No se heredan cabeceras ni se inventa registro o PSF; no se editan los originales.

`process_b1_pair` reutiliza validated_difference y export_difference para escribir
FITS/PNG/JSON en un directorio nuevo. Los metadatos adicionales sobreviven a la
serialización por FrameSpec. La desviación estándar se convierte a varianza en
memoria; no se sobreescribe el FITS. Sin ruido en ambas imágenes se conserva null
con advertencia. temporal_comparison_verified sigue false hasta revisión adicional.

Para ejecutar la integración real faltan dos archivos revisados y el payload de
adaptación con pasadas, épocas, respuesta/banda, máscaras, calibración, PSF y
registro. Variables nuevas: B2_B1_PAIR_JSON y B2_B1_DATA_ROOT. La prueba enumera
esos requisitos al omitirse; no usa una pareja sintética como sustitución.

## 10. Integración B3

Guía exacta en [B2_HANDOFF.md](B2_HANDOFF.md).

```python
from pathlib import Path
from app.b2.service import ScienceService

science = ScienceService(Path(".b2-runs/phase4-demo"))
targets = science.list_targets()
wise_status = science.get_status("WISE 0855")
metadata = science.get_observations("WISE 0855")
measurements = science.get_photometry("WISE 0855")
spectra = science.get_spectra("WISE 0855")
catalog = science.get_splices()
products = science.list_products("WISE 0855")
payload = science.summary().model_dump(mode="json")
```

No endpoints nuevos. Los getters reutilizan Pydantic; B3 decide sus rutas y errores
HTTP. El acceso a archivos es exclusivamente por inventario con resolución segura
y checksum, no por una ruta arbitraria enviada desde el navegador. Para async,
usar asyncio.to_thread u otro mecanismo del backend existente.

## 11. Demo offline y portabilidad

Desde la raíz del proyecto, con dependencias ya instaladas:

```powershell
venv/Scripts/python.exe -m app.b2.offline_demo validate --bundle .b2-runs/phase4-demo

# Directorio y archivo de salida NUEVOS:
venv/Scripts/python.exe -m app.b2.offline_demo demo --bundle .b2-runs/phase4-demo --summary .b2-runs/jury-summary.json --recompute .b2-runs/jury-replay
```

Salida 0 cuando la integridad, los cinco objetivos, SPLICES y la reproducción son
correctos. Salida 1 si falla. Éxito significa integración/reproducción, no espectros
o curvas científicas completados. El resumen JSON contiene los resultados tipados
y advertencias además de sus rutas; las funcionalidades ausentes no se simulan.

Se ejecutó sin red y bajo tests que hacen fallar conexiones socket/httpx. No se
resuelven nombres ni se llama a NASA durante demo/validate/recompute. Los mensajes
INFO de SIP se conservan; la receta existente desactiva SIP solo en el WCS espectral,
según IRSA, sin borrar el SIP astrométrico. Matplotlib puede crear su caché local
de fuentes en la primera ejecución; no necesita conexión externa.

Para reconstruir otro paquete en esta máquina, sin duplicar FITS:

```powershell
venv/Scripts/python.exe -m app.b2.offline_demo package --source .b2-runs/phase3-demo-final --cache .b2-cache --splices .b2-runs/phase3-splices-final/splices.json --output .b2-runs/another-package
```

Copiar el paquete completo a otra máquina hace materialmente disponibles sus doce
FITS y productos con rutas POSIX relativas. No basta un clone: caché/outputs están
ignorados por Git. El manifest por SHA-256 verifica integridad respecto de lo
registrado, no una firma criptográfica de NASA ni una calibración científica.

## 12. Pruebas y resultados

Se preservaron todas las pruebas anteriores. Registro final: **128 aprobadas,
2 omitidas, 2 advertencias**. Mypy sin errores en **26 archivos**, compileall,
pip check y git diff --check correctos. Python local 3.14.7.

La clasificación se añade en conftest sin reescribir las pruebas históricas:

| Marca | Contenido | Ejecución final |
|---|---|---:|
| unit | Fixtures sintéticas/contratos, integridad, rutas, fallos, B1 y WCS | 119 aprobadas |
| real_data | FITS/resultados auténticos y demo offline real | 7 aprobadas |
| nasa_ipac | Dos pruebas opt-in pequeñas SIA/SCS | 2 aprobadas |
| pending_b1 | Parejas reales histórica y adaptador nuevo | 2 omitidas |

Se verifican archivos ausentes, JSON inválido, referencias absolutas/traversal,
proveniencia incompleta, discrepancias entre JSON, checksums, fuentes sintéticas
rechazadas en modo observacional, modo external sin root, campos B1 inválidos,
ruido/varianza, conservación de originales, geometrías SIP incompatibles, estados
preliminares y reproducción con conexiones bloqueadas.

Advertencias conocidas: deprecación de TestClient/Starlette por httpx y ERFA en
la prueba sintética de movimiento propio sin distancia. No se ocultaron. No se
certifican otras versiones de Python ni emparejamiento científico real de B1.

Comando de la ejecución completa con opt-ins explícitos:

```powershell
$env:B2_DATA_ROOT = (Resolve-Path .b2-cache).Path
$env:B2_REAL_ASSET_JSON = (Resolve-Path .b2-runs/real-asset.json).Path
$env:B2_REAL_RUN_JSON = (Resolve-Path .b2-runs/rw-demo/run.json).Path
$env:B2_PHASE3_BUNDLE = (Resolve-Path .b2-runs/phase3-demo-final).Path
$env:B2_REAL_SPLICES_JSON = (Resolve-Path .b2-runs/phase3-splices-final/splices.json).Path
$env:B2_OFFLINE_BUNDLE = (Resolve-Path .b2-runs/phase4-demo).Path
$env:B2_LIVE_IRSA = "1"
$env:B2_LIVE_SPLICES = "1"
venv/Scripts/python.exe -m pytest -q --tb=short
venv/Scripts/python.exe -m mypy
venv/Scripts/python.exe -m compileall -q app
venv/Scripts/python.exe -m pip check
```

Para presentar sin red, no habilitar las marcas externas; ejecutar `pytest -m
"unit or real_data"` con los paths locales o simplemente la CLI offline. El
resultado numérico histórico de RW se comprueba como regresión de su receta
antigua, no como validación científica de esa receta.

## 13. Problemas identificados y estado de aceptación

Se resolvieron la separación de SPLICES/caché respecto al paquete, falta de
inventario verificable, falta de fachada B3, ambigüedad de disponibilidad y ruido
sigma, y el falso rechazo temporal del comparador WCS. No se trató de resolver
fondo inválido, saturación o calibración faltante inventando datos.

Los ocho criterios de integración se satisfacen en el alcance técnico: servicio
documentado, paquete verificable/reproducible, procedencia/estado conservados,
cálculos estables, adaptador B1 documentado, pruebas históricas aprobadas,
funciones pendientes identificadas y demo sin conexión. Quedan bloqueadas las
validaciones científicas que requieren nuevos productos/calibración y una pareja B1.

## 14. Recomendaciones para el jurado

1. Abrir el resumen final con los cinco objetivos y sus metadatos reales.
2. Mostrar WISE junto a flujo, error y S/N~1.16, declarando que no es detección.
3. Mostrar SPLICES como catálogo candidato con procedencia y unidades.
4. Explicar los rechazos de RW/R Dra y la diferencia entre integridad de archivos
   y validación científica; no presentar un punto como curva o espectro completo.
5. Mostrar que validar y recalcular funciona offline. Las diferencias reales
   deben figurar bloqueadas hasta B1, sin usar el ejemplo sintético como observación.

No se hicieron commits/pushes ni cambios de endpoints. La entrega es integrable,
con límites científicos explícitos y reproducibles.
