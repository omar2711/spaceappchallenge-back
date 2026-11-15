# Auditoría del repositorio e integración de B2

Fecha: 15 de noviembre de 2026, Europe/Paris. Repositorio: https://github.com/omar2711/spaceappchallenge-back.

Esta auditoría inspecciona objetos Git remotos mediante `git show` y el árbol local mediante lecturas. Se ejecutó `git fetch origin --prune`; no se integró código. El único archivo de trabajo creado para esta tarea es este informe. No se ejecutaron pipelines remotos, descargas científicas, instalaciones, commits, pushes, cambios de rama, merges, rebases, pull, stash, reset ni clean.

## 1. Estado local y conservación

Estado inicial y comprobación posterior, antes de crear este documento:

```text
## feature/b2-science
 M pyproject.toml
?? .b2-cache/
?? .b2-runs/
?? app/b2/
?? docs/
?? tests/
```

`HEAD` y la rama local `main` siguen en `17b6ba0` (`First Commit`). B2 no tiene commits: la comparación de commits con el remoto NO incluye sus archivos nuevos ni las modificaciones locales de dependencias.

Se verificaron contra `docs/b2-phase4-evidence.json` los hashes de los **26 módulos Python de B2** y de los **14 FITS originales**: todos coinciden. También coinciden los hashes de los **48 recursos inventariados** del paquete `.b2-runs/phase4-demo/`. Siguen presentes los ocho archivos de pruebas y los ocho documentos/evidencias anteriores. Estas verificaciones comprueban conservación respecto de la evidencia de fase 4, no validan por sí mismas la interpretación científica.

Material que debe preservarse por separado de Git:

- `.b2-cache/`: 14 FITS reales, 55.612.800 bytes según evidencia previa.
- `.b2-runs/`: consultas, procedencia, resultados, informes JUnit y ejecuciones previas. El paquete válido es `phase4-demo`, con 12 FITS enlazados al caché, no el intento parcial `phase4-package`.
- `app/b2/`, `tests/`, `docs/` y `pyproject.toml`: código, contratos y documentación aún sin commit.

Un commit o un `git bundle` no protegen los datos no rastreados. Una copia de respaldo debe incluir cachés/resultados; una copia normal de los hardlinks conserva contenido aunque deje de compartir bloques de disco. No ejecutar limpiadores del pipeline sobre estas carpetas.

## 2. Referencias y rama principal remota

El fetch terminó correctamente. Su primer intento encontró el bloqueo de escritura del sandbox sobre `.git/FETCH_HEAD`; el reintento con elevación autorizada actualizó las referencias. La consulta `git ls-remote --symref origin HEAD`, también fuera del bloqueo de red del sandbox, confirmó:

```text
ref: refs/heads/main HEAD
dd8af7c822ea6e22b1c9a58543d7ab65c80d35ba HEAD
```

| Referencia remota | Punta | Situación respecto de origin/main |
|---|---|---|
| `origin/main` | `dd8af7c` | Principal, ocho commits después del HEAD local |
| `origin/feature/custom-coords` | `dd8af7c` | Idéntica a main |
| `origin/feature/analysis` | `e986ab4` | Ancestro de main; main tiene tres commits posteriores |
| `origin/feature/pipeline-spherex` | `2d32ef2` | Ancestro de main; main tiene cuatro commits posteriores |
| `origin/feature/spectra` | `38c3fe0` | Contiene main y dos commits adicionales |

`git rev-list --left-right --count HEAD...origin/main` devolvió `0 8`. No hay divergencia entre commits locales y main remoto; sí existe una implementación local importante fuera del historial.

## 3. Commits nuevos

Del más antiguo al más reciente; todos atribuidos en Git a `spectria-agency`:

| Commit | Destino observado | Cambio |
|---|---|---|
| `6d82414` | main | Reglas de exclusión de datos |
| `32af38e` | main | Pipeline SPHEREx B1 |
| `47669c9` | main | WebP y manifests de los cinco objetivos |
| `2d32ef2` | main | Documentación de pipeline y README |
| `e986ab4` | main | Análisis T1: diferencias; T2: curvas de luz |
| `1181a6c` | main | Corrección de descripción BKGSUB: ZODI + plano |
| `6ec73ce` | main | Coordenadas arbitrarias y trabajos en segundo plano |
| `dd8af7c` | main | Dos exposiciones/grupo por defecto y presets de demo |
| `76d73e6` | Solo feature/spectra | T3: espectrofotometría forzada |
| `38c3fe0` | Solo feature/spectra | T4: catálogo SPLICES y candidata de hielo |

Las fechas de autor son del 14 de noviembre, zona `-04:00`; las dos últimas corresponden al 15 de noviembre en París. Son nuevos respecto de nuestra base `17b6ba0`; no puede inferirse cuándo los leyó por última vez cada integrante.

## 4. Archivos agregados y modificados

`HEAD..origin/main`: **291 archivos afectados: 289 agregados, dos modificados, ninguno eliminado; 24.240 líneas agregadas**. Los modificados son `.gitignore` y `README.md`. `pyproject.toml` y `app/main.py` remotos son idénticos a nuestra base comprometida.

Inventario de adiciones fuera de los productos WebP:

```text
CLAUDE.md
CONTRIBUTING.md
analysis/README.md
analysis/__init__.py
analysis/analysis.schema.json
analysis/build.py
analysis/common.py
analysis/diff.py
analysis/lightcurve.py
analysis/photometry.py
analysis/requirements.txt
docs/analysis_t1_t2.md
docs/decisiones.md
docs/pipeline_estado.md
docs/pipeline_fase1.md
docs/pipeline_fase2.md
docs/pipeline_fase5.md
pipeline/README.md
pipeline/__init__.py
pipeline/build.py
pipeline/check_flags.py
pipeline/custom.py
pipeline/deep.py
pipeline/explore_barnard.py
pipeline/export.py
pipeline/fetch.py
pipeline/manifest.schema.json
pipeline/report.py
pipeline/requirements.txt
pipeline/stack.py
pipeline/targets.py
pipeline/targets.yaml
public-data/custom/presets.json
public-data/custom/c2d9e7410cce7/manifest.json
public-data/custom/c849cdb29dee1/manifest.json
public-data/custom/cd2f34edd4880/manifest.json
public-data/targets/index.json
public-data/targets/{barnard,eps_ind_b,wise0855,rw_aur,r_dra}/manifest.json
public-data/targets/{barnard,eps_ind_b,wise0855,rw_aur,r_dra}/analysis.json
```

La notación entre llaves representa los cinco archivos de cada grupo. Main tiene **242 WebP**: frames de los cinco objetivos, diferencias/profundas y tres campos custom precalculados. No son FITS aptos para fotometría: son visualizaciones con stretch y cuantización.

`origin/main..origin/feature/spectra` modifica 17 rutas:

```text
analysis/README.md
analysis/analysis.schema.json
analysis/build.py
analysis/custom_spectrum.py                 (nuevo)
analysis/photometry.py
analysis/spectra.py                         (nuevo)
analysis/splices.py                         (nuevo)
docs/analysis_t3_t4.md                       (nuevo)
docs/figures/spectrum_eps_ind_b.png          (nuevo)
public-data/catalogs/splices.json            (nuevo)
public-data/custom/c2d9e7410cce7/analysis.json (nuevo)
public-data/custom/cd2f34edd4880/analysis.json (nuevo)
public-data/targets/{barnard,eps_ind_b,wise0855,rw_aur,r_dra}/analysis.json
```

El detalle exhaustivo de nombres de imágenes se obtiene sin modificar archivos con `git diff --name-status HEAD origin/main` y `git diff --name-status origin/main origin/feature/spectra`.

## 5. Arquitectura observada

| Capa | Implementación verificada por lectura | Límite de esta auditoría |
|---|---|---|
| API FastAPI | `app/main.py`: únicamente GET `/` y GET `/health` | No hay nuevos endpoints científicos, custom ni archivos estáticos montados |
| B1 | `pipeline/`: SIA, descargas, reproyección, combinación, exportación, CLI y jobs | No se ejecutó el pipeline ni se recibieron sus FITS |
| Análisis remoto | `analysis/`: T1/T2; T3/T4 adicionales en spectra | Código y productos presentes; sin suite remota de tests |
| Nuestro B2 | `app/b2/`: contratos Pydantic, ScienceService, caché, cálculos, paquete offline, pruebas | Continúa local y sin integración con analysis/ |
| Datos para web | `public-data/`: JSON + WebP; SPLICES en spectra | Existencia y referencias verificadas; interpretación científica pendiente |
| Luna, Marte, Cochabamba y 3I/ATLAS | Objetivos descritos en CLAUDE.md/decisiones | No se encontraron implementaciones remotas de esas funcionalidades |

`CLAUDE.md` dibuja una futura carpeta `api/`, pero no existe en las referencias auditadas. No hay routers B3, modelos Pydantic nuevos de API ni importaciones de `ScienceService`. `pipeline.Spec` es un dataclass; manifests y análisis usan diccionarios y JSON Schema. El esquema remoto de análisis deja `spectra` y `reference_bands` como arrays sin estructura interna especificada.

El título del commit `dd8af7c` menciona API, pero sus utilidades están preparadas para ser llamadas por una API futura: no añade rutas HTTP. La documentación `pipeline_estado.md` conserva un pendiente de integrar B1 a main que ya está obsoleto según la ascendencia Git comprobada.

## 6. Estado real de B1 y parejas temporales

B1 es una implementación sustancial, no una carpeta vacía. `fetch.py` consulta `spherex_dr1` y `spherex_qr3`, registra índices ECSV y descarga recortes con reintentos. `stack.py` resta ZODI y un plano de cielo, reproyecta a grilla TAN común y combina por pasada/detector. Marca píxeles saturados rellenados en FILLED. `export.py` produce WebP y manifest; `custom.py` ofrece funciones bloqueantes y jobs con un trabajador por proceso, estado persistido y reutilización de caché.

Productos publicados comprobados:

| Objetivo | Pasadas | Frames | Diferencias publicadas | Con aviso wavelength_mismatch |
|---|---:|---:|---:|---:|
| Barnard | 3 | 18 | 12 | 4 |
| Epsilon Indi B | 4 | 22 | 16 | 14 |
| WISE 0855 | 3 | 18 | 12 | 10 |
| RW Aurigae | 3 | 18 | 12 | 9 |
| R Draconis | 3 | 18 | 12 | 7 |
| **Total** | | **94** | **64** | **44** |

**No se encontró ninguna pareja FITS real entregada por B1 que pueda validarse en este entorno.** Ninguna rama remota auditada contiene FITS/ECSV; localmente tampoco existen `data/`, `pipeline/`, `analysis/` o `public-data/`. Los manifests referencian nombres como `S1_D1.fits`, pero los archivos se generan en `data/processed/` y no se versionan. Los FITS de `.b2-cache/` son nuestros recortes anteriores, no estos stacks B1.

El código permite conocer el formato esperado, pero no comprobar dimensiones reales, WCS, píxeles, máscaras ni calibración de una pareja concreta. Pedir a B1 una pareja pequeña con todos sus HDU y procedencia es preferible a regenerar gigabytes.

### Incompatibilidades concretas con B1Frame

| Requisito de nuestro adaptador | Producto remoto observado | Consecuencia |
|---|---|---|
| DETECTOR, MJD-OBS y TIMESYS en HDU de imagen seleccionado | DETECTOR y DATE-MID en PRIMARY; IMAGE lleva grilla y BUNIT; no se escriben esos campos temporales requeridos en IMAGE | Rechazo actual; necesita adaptación explícita y documentada, sin inventar tiempos |
| Varianza en unidades cuadradas de IMAGE | stack.py reutiliza header BUNIT="MJy/sr" también en VARIANCE | Error dimensional del header; debe aclararse/corregirse en una tarea autorizada |
| Máscara FLAGS y máscara independiente de cielo | Stack entrega FILLED y NIMAGES, sin FLAGS ni máscara de cielo | FILLED no sustituye ambas máscaras; definir validez y fondo con B1 |
| response_id/band_id efectivos compatibles | Se entrega detector y rango/longitudes de las exposiciones | Mismo detector no demuestra misma respuesta espectral |
| calibration_id, psf_match_id y evidencia | El manifest no los ofrece | No crear etiquetas ficticias para superar validación |
| Procedencia, versión, URL y hash por recurso | Manifest ofrece colecciones/generación; EXPOSURES tiene obs_id/colección; índices raw contienen access_url | Falta el enlace verificable de cada producto al material de origen |
| Épocas explícitas y distintas | DATE-MID y tabla EXPOSURES permiten documentarlas | Falta comprobar FITS y escala temporal, no asumirla por el texto ISO |

Puntos de código para revisión posterior: `pipeline/stack.py:200` interpola varianza como una imagen; eso no implementa propagación completa mediante pesos cuadrados ni covarianza de reproyección. `:219` y `:247` explican el problema de BUNIT. `:224–229` ubican detector/fecha en PRIMARY. La grilla común es una intención visible del constructor; aún requiere validación en los archivos entregados y una revisión de PSF/bandas.

## 7. Estado de B3

**B3 todavía no está conectado a B1 ni a B2 en el backend auditado.** `app/main.py` es idéntico al original. No hay endpoints de trabajos, objetivos, espectros, curvas, diferencias, catálogo o productos. Tampoco hay servicio HTTP de Luna/Marte.

Hay puntos de integración listos para usar después de acordar contratos:

- B1: `submit_custom`, `get_status` y `build_for_coords`.
- Nuestro B2: `ScienceService.list_targets/get_result/get_observations/get_photometry/get_spectra/get_splices/get_differences/list_products/resolve_product/get_status/summary`.
- Demo web: JSON y WebP remotos con rutas relativas.

Los jobs remotos usan memoria/locks de un proceso, no una cola compartida. Antes de exponerlos con varios workers deben revisarse concurrencia, persistencia, límites, rutas de job_id y recuperación. `get_status` puede escribir estado; `clear_custom` borra directorios y `build_for_coords` elimina raw FITS por defecto. No se llamó a esas funciones durante la auditoría. La retención por defecto es incompatible con un análisis posterior que necesite fotometría por exposición si no se conserva otra copia.

## 8. Compatibilidad y duplicación con nuestro B2

Existe **duplicación funcional significativa**, aunque las rutas no colisionan:

| Función | Nuestro B2 | Remoto |
|---|---|---|
| Acceso y caché SPHEREx | archive/pipeline | pipeline/fetch |
| Diferencias | validated_images/difference_export/b1_adapter | analysis/diff |
| Fotometría y curvas | photometry/lightcurves/pipeline | analysis/photometry/lightcurve |
| Espectros | spectra/spectral_products | analysis/spectra, solo spectra |
| SPLICES | catalog/catalog_snapshot | analysis/splices, solo spectra |
| Servicio tipado y paquete verificado | service/offline_bundle | Sin equivalente conectado |

No se puede importar un `analysis.json` directamente como resultado de nuestro servicio: difieren contratos, procedencia, estados científicos y formato de productos. Nuestro modo observacional exige integridad y distingue disponible/preliminar/incompleto/no disponible/bloqueado. El remoto ofrece booleanos `usable`, `significant`, `lower_limit` y avisos `caveats`; los booleanos no equivalen a detección validada.

Otros desacuerdos a resolver:

- Identificadores: remoto `barnard`, `eps_ind_b`, `wise0855`, `rw_aur`, `r_dra`; nuestro paquete usa nombres legibles. Necesita mapa estable y explícito.
- Unidades: remoto fotometría/espectros en mJy; nuestro paquete incluye Jy y metadatos de unidad. Convertir valores e incertidumbres juntos.
- Coordenadas: remoto conserva Gaia/Sesame y épocas de catálogo; nuestro B2 conserva resolución SIMBAD/procedencia propias. Debe revisarse identidad y propagación, no reemplazar un catálogo silenciosamente.
- Productos: WebP remotos frente a FITS/JSON/CSV/PNG inventariados localmente; no cambiar extensiones sin ampliar contratos y verificaciones.
- Geometría: target_px del WebP tiene y invertida; no confundir con coordenadas FITS de tabla/HDU.
- SPLICES: catálogo remoto compacto columns+rows con heurística de prioridad; nuestro snapshot conserva metadatos y consulta de cono verificable.

No se necesita modificar hoy `ScienceService` para aceptar código remoto. Una futura integración debería conservarlo y añadir un adaptador revisado para manifiesto B1 y, si se acuerda consumir resultados analysis/, un DTO distinto que preserve origen, calidad y límites. Primero decidir con el equipo cuál es la implementación científica canónica.

## 9. Revisión científica del análisis remoto

Se comprobó código y contenido publicado, no las mediciones desde sus exposiciones originales. No se incorporan sus afirmaciones como conclusiones científicas de nuestro B2.

1. **Diferencias:** `analysis/diff.py:124` resta antes de evaluar el aviso espectral (`:169`). No comprueba igualdad efectiva de banda, WCS, BUNIT o PSF: confía en B1 y calcula incluso cuando hay mismatch. 44/64 productos lo declaran. Los otros 20 no quedan automáticamente validados; el corte del aviso usa diferencia de longitudes medias >1%, no identidad de respuesta completa. Se calcula una imagen de ruido formal, pero no se exporta como FITS validado; el residual usa ruido empírico y no incluye explícitamente incertidumbre de k/PSF.
2. **Saturación y errores:** el pipeline rellena núcleos para visualización. La fotometría remota también rellena huecos y los llama cotas inferiores; no deben usarse como medidas normales. `analysis/photometry.py:78` marca saturación según huecos, no todos los bits de saturación sobre píxeles finitos; existe riesgo de etiquetar `ok` un núcleo con otros indicadores de saturación. Sustituye varianzas inválidas por máximos (`:61`), diferente de nuestro rechazo estricto.
3. **Curvas:** ajusta flujo=S(lambda)*g(época), con forma espectral compartida y piso sistemático de 3%. Es un modelo implementado, no una comparación directa de bandas idénticas. Falta cuantificar degeneración cobertura espectral/época e incertidumbre del ajuste de forma en cada curva. R Dra publica curvas basadas en cotas inferiores; RW Aur tiene booleanos de variabilidad. No reemplazan nuestras curvas aún no validadas.
4. **Espectros en feature/spectra:** hay espectros por pasada y combinado para cinco objetivos, con índices/profundidades y exclusión de cotas inferiores en mediciones de bandas. La documentación afirma detecciones de H2O/CH4 en Epsilon Indi B; no se reprodujeron aquí ni se dispone de los originales para confirmarlas. El umbral formal `significant` de índices no basta para atribución molecular; ventanas, continuo, resolución, errores, contaminación y variabilidad requieren revisión. El propio remoto advierte que marcadores de bandas no son detecciones y que SPLICES es lista de candidatas.
5. **Precisión SPLICES:** `analysis/splices.py:61` redondea todos los floats a tres decimales antes del posterior redondeo RA/Dec a seis (`:73`). Las 2.293 posiciones publicadas efectivamente tienen solo tres decimales de grado: el redondeo puede introducir hasta ~1,8 arcsec por eje angular. El formato compacto (`:83`) además omite source_id aunque el procesamiento intermedio lo conserva. Deben preservarse precisión e identidad para cruces astrométricos y el contrato local.
6. **Datos publicados:** todos los JSON de main y spectra se pudieron parsear sin constantes NaN/Infinity; todas las referencias WebP de manifests y análisis apuntan a objetos versionados existentes. Esto confirma coherencia estructural básica. No se ejecutó validación JSON Schema completa ni extracción de fotometría desde FITS.

Nuestro resultado conocido sigue siendo parcial: una medida preliminar de WISE 0855 con SNR ~1,157 no es detección; no hay curvas completas, espectros completos ni diferencias temporales reales validadas en el paquete local. La mayor cantidad de exposiciones del equipo puede habilitar mejores resultados, pero no debe atribuirse al paquete B2 actual.

## 10. Conflictos de archivos y dependencias

**Hechos comprobados:** ninguna ruta remota de main o spectra coincide con nuestros archivos no rastreados. No hay conflicto add/add identificado para `app/b2/`, nuestros tests o nuestros docs. La única modificación rastreada local es `pyproject.toml`; remoto no lo modificó. No se detecta conflicto textual de tres vías previsible con las puntas actuales, pero no se ejecutó ninguna fusión y no se garantiza una futura sin conflictos.

Cambian `.gitignore` y `README.md`, ambos sin modificación local rastreada. `.gitignore` remoto añade `data/`, `*.fits`, archivos temporales y formatos grandes: protege de publicar crudos, pero puede ocultar FITS locales en posteriores listados. No ignora por completo `.b2-runs/` y sus JSON/CSV/PNG. Evitar `git add .` y revisar explícitamente todo lo preparado para commit.

**Dependencias:** no hay rangos numéricos demostrablemente incompatibles entre nuestro pyproject y los requirements remotos; sus restricciones son mayormente más abiertas. No existe lock conjunto ni ensayo de resolución. El entorno actual carece de **reproject, scipy, photutils, jsonschema y psutil**; por ello no puede ejecutarse todo el pipeline remoto. YAML, requests y Pillow sí están disponibles. No se instaló nada.

`pip install -e .[dev,b2-real]` no incorpora esas nuevas dependencias. Además setuptools incluye solamente `app*`: `pipeline/` y `analysis/` no quedan incluidos como paquetes instalables en una distribución construida con la configuración actual. Importarlos desde raíz y distribuirlos como wheel son situaciones diferentes. Debe acordarse entorno de datos separado o extras/paquetes conjuntos en otra tarea autorizada.

## 11. Riesgos de sincronización y recomendación

El fetch fue seguro para el árbol de trabajo y está completado. **No recomiendo integrar ahora con B2 aún sin respaldo ni commits.** La baja probabilidad de conflicto textual no elimina el riesgo de pérdida del trabajo no rastreado ni la duplicación científica.

Prioridades antes de autorizar sincronización:

1. Copia externa verificable de código, cachés y resultados; fijar una instantánea local de B2 mediante commit solo con autorización.
2. Acordar con el equipo propiedad/canon de `analysis/` frente a `app/b2/` y contrato público para B3.
3. Pedir a B1 una pareja FITS pequeña, índices/procedencia, máscaras, unidades, tiempos y evidencia de banda/PSF/alineación. No descargar todo el dataset para esta comprobación.
4. Integrar primero main en un paso controlado; revisar spectra por separado, dado que todavía no está en main.
5. Resolver por revisión explícita las incompatibilidades de metadatos, unidades y criterios científicos, sin relajar validaciones para aceptar productos automáticamente.
6. Ejecutar regresión local y luego pruebas de integración con datos B1; conectar endpoints B3 en una tarea posterior.

Oportunidad inmediata tras autorización: reutilizar manifests/WebP para visualización con avisos y conectar consultas de solo lectura de ScienceService. Eso no requiere declarar válidas las curvas/diferencias del remoto.

## 12. Secuencia Git recomendada, NO ejecutada

Los siguientes comandos son una propuesta para después de autorización explícita. Incluyen commits y merge prohibidos para esta auditoría; no deben ejecutarse todavía. Se mantiene la rama `feature/b2-science`, sin reset, clean, stash ni checkout.

### A. Respaldar fuera del repositorio

PowerShell, desde la raíz del proyecto, con destino nuevo. No usar opciones de borrado/espejo:

```powershell
git status --short --branch
$auditBackup = Join-Path (Split-Path (Get-Location).Path -Parent) ('b2-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $auditBackup) { throw 'El destino ya existe' }
New-Item -ItemType Directory -Path $auditBackup
robocopy . $auditBackup /E /COPY:DAT /R:1 /W:1 /XD .git .venv venv __pycache__ .pytest_cache .mypy_cache
if ($LASTEXITCODE -ge 8) { throw 'El respaldo falló; detenerse' }
git bundle create (Join-Path $auditBackup 'repository.bundle') --all
```

La copia cubre los archivos no rastreados, también FITS ignorados; el bundle cubre el historial y referencias, no el árbol local. Antes de continuar, verificar hashes de FITS, recursos inventariados y fuentes en la copia contra la evidencia de fase 4. No basta con que robocopy termine. La escritura del respaldo externo necesitará permisos correspondientes.

### B. Fijar B2 con autorización para commit

```powershell
git add -- pyproject.toml app/b2 tests docs/B2.md docs/B2_PHASE2.md docs/B2_PHASE3.md docs/B2_PHASE4.md docs/B2_HANDOFF.md docs/B2_REPOSITORY_AUDIT.md docs/b2-phase2-evidence.json docs/b2-phase3-evidence.json docs/b2-phase4-evidence.json
git diff --cached --stat
git diff --cached --name-only
git diff --cached --check
```

Revisar el contenido completo preparado: sin secretos, FITS ni `.b2-cache/` o `.b2-runs/`. Solo después de aprobar esa revisión:

```powershell
git commit -m "feat(b2): preserve validated science service and offline integration"
git status --short --branch
git fetch origin --prune
git log --oneline --decorate HEAD..origin/main
git diff --stat HEAD...origin/main
```

Los datos seguirán no rastreados; eso es esperado. Repetir la revisión de colisiones de rutas si el fetch cambia las puntas desde las auditadas.

### C. Integración controlada, con autorización separada

```powershell
git merge --no-ff --no-commit origin/main
git status --short --branch
git diff --cached --stat
git diff --cached --check
```

`--no-ff --no-commit` fuerza una pausa de revisión incluso si sería posible avanzar directamente. Ante conflictos, detenerse y revisarlos con el usuario; no resolver ni sobrescribir automáticamente. Antes del commit de integración, ejecutar pruebas y revisión de dependencias/contratos según el apartado siguiente. Solo con nueva aprobación, crear el commit de integración. No se propone push automático.

No integrar `feature/spectra` en este mismo paso. Revisar después sus dos commits y resolver la precisión/identidad SPLICES y criterios científicos antes de autorizar su incorporación.

## 13. Pruebas conocidas y verificaciones pendientes

Evidencia local existente, leída del JUnit de fase 4:

- `.b2-runs/phase4-tests.xml`: 130 casos, **128 aprobados, dos omitidos**, cero errores/fallos. Las dos omisiones corresponden a integración con pareja B1 real ausente.
- `.b2-runs/phase4-contract-tests.xml`: dos casos aprobados para contrato tipado final y CLI offline/reproducción.
- Evidencia previa: mypy sin errores en 26 módulos, reproducción offline de cinco objetivos, una medida comparada sin discrepancias.
- Auditoría actual: hashes B2/caché/paquete conservados; AST de los 19 archivos Python de main y los 22 de spectra sin errores de sintaxis; JSON parseable, referencias WebP existentes y ninguna colisión con rutas locales no rastreadas.

No se volvió a ejecutar pytest, mypy, pipelines ni imports remotos: se evitó modificar cachés/artefactos existentes y faltan dependencias. **No hay pruebas automatizadas versionadas en ninguna de las ramas remotas inspeccionadas.** Scripts `report` y documentación de regresión manual no equivalen a una suite ejecutada aquí.

Después de integrar y preparar un entorno autorizado, la regresión mínima local puede ejecutarse con los datos ya disponibles, sin habilitar las consultas live:

```powershell
$env:B2_LIVE_IRSA = '0'
$env:B2_LIVE_SPLICES = '0'
$env:B2_DATA_ROOT = (Resolve-Path .b2-cache).Path
$env:B2_REAL_ASSET_JSON = (Resolve-Path .b2-runs/real-asset.json).Path
$env:B2_REAL_RUN_JSON = (Resolve-Path .b2-runs/rw-demo/run.json).Path
$env:B2_PHASE3_BUNDLE = (Resolve-Path .b2-runs/phase3-demo-final).Path
$env:B2_REAL_SPLICES_JSON = (Resolve-Path .b2-runs/phase3-splices-final/splices.json).Path
$env:B2_OFFLINE_BUNDLE = (Resolve-Path .b2-runs/phase4-demo).Path
venv/Scripts/python.exe -m pytest -q
venv/Scripts/python.exe -m mypy
venv/Scripts/python.exe -m pip check
```

La cifra de aprobados/omitidos puede variar al no habilitar los dos tests live; no exigir 128 aprobados si las consultas están desactivadas. Sigue pendiente validar los JSON Schema completos del remoto, ejecutar sus módulos con dependencias compatibles y FITS reales, comprobar reproyección/varianzas/PSF/bandas, probar endpoints B3 cuando existan y verificar instalación/distribución desde fuera de la raíz.

## Conclusión

El equipo avanzó en adquisición SPHEREx, procesamiento por pasadas, visualización y análisis precalculado. B1 es utilizable como fuente candidata de productos, pero aún falta recibir y validar sus FITS para nuestro contrato. B3 mantiene únicamente la API base. Nuestro B2 está preparado como servicio tipado y demo offline, no como consumidor automático de los formatos remotos.

El siguiente paso es revisar este diagnóstico con el equipo, respaldar B2 y autorizar una sincronización controlada de main. La integración no se ha ejecutado ni se declara exitosa. Las cuestiones científicas y la duplicación de implementaciones deben resolverse antes de exponer resultados unificados.
