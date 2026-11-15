# B2 → B3: interfaz de servicio y paquete offline

Fecha: 15/11/2026. Rama `feature/b2-science`. No se crearon endpoints de B3.

## Configuración mínima

El directorio preparado es `.b2-runs/phase4-demo/`. Es un paquete de lectura con
`manifest.json`, el índice original, los productos, SPLICES y `data/` con doce
recortes FITS necesarios. En esta máquina los FITS son enlaces duros al caché:
no se duplicaron sus bytes. Copiar/archivar **solo este paquete** a otra máquina
transporta los archivos necesarios, sin necesitar los otros dos recortes de prueba
de fondo ni rutas absolutas de la máquina original.

El caché y los resultados están ignorados por Git; un clone no los incorpora.
Se requieren las dependencias existentes `.[b2-real]` antes de desconectar la red.
No ejecutar pip ni resolver nombres durante la presentación.

```python
from pathlib import Path
from app.b2.service import ScienceService, ScienceServiceError

# Configuración del servidor, nunca un directorio enviado por el navegador.
science = ScienceService(Path(".b2-runs/phase4-demo"))
```

La construcción valida JSON, rutas, referencias cruzadas, procedencia, unidades y
checksums. Un paquete inválido produce `ScienceServiceError(code="invalid_package")`.
Para diagnosticarlo sin ocultar los fallos:

```python
from app.b2.offline_bundle import validate_bundle

report = validate_bundle(Path(".b2-runs/phase4-demo"))
print(report.model_dump(mode="json"))
```

## Funciones listas para consumir

Todos los modelos son Pydantic v2 y reutilizan TargetResult, Observation,
Measurement, SpectralProduct, SplicesSnapshot y DifferenceArtifacts ya existentes.
Los estados de disponibilidad y el inventario son los únicos contratos nuevos
de presentación/almacenamiento; no replican los cálculos científicos.

```python
targets = science.list_targets()                      # list[Target]
status = science.get_status("WISE 0855")               # TargetStatus
result = science.get_result("WISE 0855")               # TargetResult completo
observations = science.get_observations("WISE 0855")   # list[Observation]
photometry = science.get_photometry("WISE 0855")        # list[Measurement]
spectra = science.get_spectra("WISE 0855")              # list[SpectralProduct]
splices = science.get_splices()                        # SplicesSnapshot | None
differences = science.get_differences("RW Aurigae")    # [] actualmente
products = science.list_products("WISE 0855")          # list[BundleFile]
summary = science.summary()                           # DemoSummary

# DTOs convertibles a JSON y compatibles con respuestas FastAPI:
payload = result.model_dump(mode="json")
summary_payload = summary.model_dump(mode="json")
```

El resumen incorpora los cinco estados, metadatos de observaciones, fotometría,
muestras espectrales, SPLICES, diferencias registradas, advertencias e inventario.
No contiene píxeles FITS embebidos ni rutas absolutas del servidor.

`get_observations` devuelve las filas de la búsqueda acotada (48 por objetivo),
no 48 descargas. `result.run.cutouts` identifica los archivos realmente adquiridos,
sus URLs, fechas, detector, colección y SHA-256. No se interpreta una búsqueda
truncada como cobertura completa del archivo.

Los identificadores exactos son:

```python
["Barnard's Star", "Epsilon Indi B", "WISE 0855", "RW Aurigae", "R Draconis"]
```

## Estados que el frontend debe preservar

| Funcionalidad | Estado actual |
|---|---|
| Metadatos de los cinco objetivos | available |
| Fotometría WISE 0855 | preliminary |
| Muestras espectrales WISE 0855 | incomplete; una muestra, no espectro completo |
| Fotometría/espectros aceptados de los otros cuatro | unavailable |
| Curvas validadas | unavailable |
| Diferencias reales | blocked, pendiente B1 |
| SPLICES | available; una fuente candidata |

`processing_status="failed"` describe el cálculo científico de ese objetivo,
no la integridad del paquete ni la disponibilidad de sus metadatos. No ocultar
los objetivos cuyo análisis fue rechazado.

Para WISE 0855:

```python
m = science.get_photometry("WISE 0855")[0]
snr = m.flux_jy / m.uncertainty_jy  # ~1.16 en los datos conservados
assert m.status == "preliminary_aperture"
```

No mostrar “detectado”. `accepted` significa que la muestra pasó las validaciones
implementadas, no que haya una fuente significativa. `detection_claim` permanece
`"none"`. `usable_samples` no certifica un espectro completo ni flujo total.
Mantener `warnings`, método, unidades, errores, fecha y S/N visibles.

La medición histórica de RW Aurigae de fase 2 no forma parte de las medidas
aceptadas actuales: su fondo no supera la máscara SOURCE. R Draconis tampoco
tiene medidas temporales compatibles aceptadas en el caché inspeccionado.
Los marcadores H2O, CO2 y CO son referencias de longitud de onda; no detecciones.
SPLICES es un catálogo de candidatos, y sus magnitudes no son fotometría SPHEREx.
Conservar los IDs grandes como strings en JavaScript.

## Archivos y seguridad de rutas

```python
image = next(p for p in science.list_products("WISE 0855")
             if p.path.endswith("spectral-0/spectrum.png"))
local_file = science.resolve_product(image.path)  # Path interno, solo lectura

# Uso dentro de la capa HTTP que implemente B3, sin registrar rutas aquí:
from fastapi.responses import FileResponse
response = FileResponse(local_file, media_type=image.media_type)
```

`resolve_product` solo admite entradas exactas del inventario y revalida tamaño y
SHA-256. Rechaza productos desconocidos, traversal, drive/UNC, ADS, enlaces
simbólicos y rutas que salgan del root. No pasar una ruta libre del cliente a
FileResponse ni serializar `local_file` como ruta de Windows. El DTO público
`BundleFile.path` es relativo y portable. No servir el árbol de caché completo.

Los FITS enlazados comparten almacenamiento con el caché: no editarlos ni abrirlos
en modo update. Si cambian, la validación falla. En una instalación que no permita
enlaces duros, construir en modo `external` y configurar un `data_root` explícito
en ScienceService/validate_bundle; ese modo no es autónomo hasta aportar ese root.
No se copian silenciosamente decenas de MB cuando falla un enlace.

Los getters realizan lectura de disco; en endpoints async utilizar, por ejemplo,
la biblioteca estándar, sin reimplementar ciencia:

```python
import asyncio

async def load_science_result(target_id: str):
    return await asyncio.to_thread(science.get_result, target_id)
```

Errores estables de servicio: unknown_target, unknown_product, invalid_package,
missing_product, unsafe_product y checksum_mismatch. B3 decide el mapeo HTTP
(por ejemplo 404 para IDs desconocidos, 503 para almacenamiento inválido); B2
no altera las rutas existentes ni expone el root absoluto en esos mensajes.

## Recepción de B1: adaptador B2, no manifest impuesto a B1

```python
from app.b2.b1_adapter import B1Frame, process_b1_pair

def analyze_registered_pair(science_payload: dict, reference_payload: dict,
                            configured_data_root: Path, new_output: Path):
    a = B1Frame.model_validate(science_payload)
    b = B1Frame.model_validate(reference_payload)
    return process_b1_pair(a, b, configured_data_root, new_output)
```

Cada B1Frame extiende FrameSpec y contiene:

- `target: Target`, `mjd`, `time_scale` (`utc`, `tt` o `tdb`), `pass_id`, `band_id`.
- `image`, `flags`, `background_mask`: FitsAsset con ruta relativa, HDU explícito
  y Provenance. La máscara de fondo usa no-cero para cielo vacío válido.
- `variance` **o** `uncertainty` (desviación estándar), opcionales y mutuamente
  excluyentes. Sus BUNIT deben corresponder al cuadrado o a la unidad de IMAGE.
- `detector`, `response_id`, `calibration_id`, `psf_match_id` explícitos.
- `registration_evidence`, `psf_evidence` y `metadata_provenance` explícitos.
- `declared_unit` y `declared_wcs` opcionales; si se envían deben coincidir con FITS.

La época debe coincidir con MJD-OBS del HDU seleccionado dentro de 1e-6 días
(0.0864 segundos), y TIMESYS debe coincidir. No se heredan cabeceras de PRIMARY
ni se inventan metadatos faltantes. Los dos objetivos y bandas efectivas deben
coincidir, las pasadas/épocas ser distintas y las cuadrículas celestes/SIP,
unidades, detectores, respuesta, calibración y PSF ser compatibles. No basta con
igualar dimensiones o un detector genérico como D6.

Los IDs y textos de evidencia son atestaciones de B1; no sustituyen revisión
empírica de registro/PSF. `temporal_comparison_verified` sigue false: una diferencia
algebraica no confirma un cambio. No se modifican los originales. El resultado
retiene las pasadas, épocas y evidencia, además de FITS/PNG/JSON y checksums.

Cuando haya una diferencia observacional revisable, puede incluirse explícitamente
su directorio en `export_bundle(..., differences=[directory])`. Los directorios
sintéticos se rechazan en modo observacional; no se descubre/añade una diferencia
por glob indiscriminado. Actualmente no hay ninguna diferencia real que registrar.

## Demostración exacta, sin internet

```powershell
venv/Scripts/python.exe -m app.b2.offline_demo validate --bundle .b2-runs/phase4-demo

# Ambos outputs deben ser NUEVOS.
venv/Scripts/python.exe -m app.b2.offline_demo demo --bundle .b2-runs/phase4-demo --summary .b2-runs/jury-summary.json --recompute .b2-runs/jury-replay
```

Salida 0: integridad/demo correctas. Salida 1: fallo; no se declara éxito ni se
simulan consultas. La demo muestra los cinco objetivos, SPLICES y estados aunque
las curvas/espectros/diferencias sigan pendientes. Recompute reutiliza la receta
científica existente y compara medidas, errores y longitudes de onda, sin red.

Outputs ya comprobados: `.b2-runs/phase4-final-summary.json` y
`.b2-runs/phase4-final-replay/`. El resumen es un resultado concreto para B3; la
reproducción adicional no copia los FITS ni sobrescribe los productos previos.

Pruebas: `pytest -m unit`, `pytest -m real_data`, `pytest -m nasa_ipac`,
`pytest -m pending_b1`, con las variables del informe B2_PHASE4.md.

La integración técnica está preparada. La conclusión científica sigue siendo:
una estimación preliminar de baja S/N, cero curvas/espectros completos validados
y ninguna diferencia temporal real confirmada.
