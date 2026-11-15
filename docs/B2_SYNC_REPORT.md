# B2 fase 5 — sincronización controlada con main

Fecha: 15/11/2026, Europe/Paris. Rama conservada: `feature/b2-science`.

**Resultado:** `origin/main` quedó integrado mediante merge local, sin conflictos y con la línea base reproducida: **128 pruebas aprobadas, dos omitidas**. No se hizo push ni se fusionó `feature/spectra`. No se alteraron algoritmos B1, endpoints B3 ni código científico B2.

La sincronización Git y la regresión B2 están verificadas. Esto no certifica ejecución completa de B1 ni integración científica B1→B2→B3: siguen pendientes sus datos, contratos y dependencias opcionales.

## 1. Estado inicial y final

Estado inicial:

```text
## feature/b2-science
 M pyproject.toml
?? .b2-cache/
?? .b2-runs/
?? app/b2/
?? docs/
?? tests/
```

HEAD inicial: `17b6ba0ec21c0b8e5b51873319aaef2aa229bdd4`. B2 estaba sin commits.

Estado tras el merge y antes de este informe:

```text
## feature/b2-science
?? .b2-cache/
?? .b2-runs/
```

Este informe se registra en un commit documental separado después del merge. El estado final esperado y comprobado es sin modificaciones rastreadas, manteniendo los dos directorios anteriores: sus archivos `.gitignore` locales siguen no rastreados y sus datos continúan excluidos. No se añadió una regla global ni se borraron esos archivos para ocultar el estado.

## 2. Respaldo y recuperación comprobada

Directorio externo al repositorio, conservado:

```text
C:\Users\fcff_\.codex\visualizations\2026\11\14\01a1dc2f-9a00-75d1-9316-4bf056023cb3\b2-phase5-backup-20261115-030408
```

Contenido:

- `working-tree.zip`: 109.447.620 bytes. Contiene 417 archivos, 110.040.503 bytes lógicos: código, pruebas, documentación, configuraciones y todos los datos/resultados B2 anteriores.
- `backup-manifest.json`: rutas relativas, tamaños y SHA-256 de cada archivo, hash del ZIP, rama y HEAD originales y verificación del bundle.
- `recovery-check/`: extracción completa del ZIP; se verificaron tamaño y SHA-256 de **los 417 archivos recuperados** contra sus originales.
- `repository-before-sync.bundle`: historial y referencias anteriores; `git bundle verify` correcto.
- `repository-after-sync.bundle`: historial protegido posterior, incluido B2, merge e informe; verificado al cerrar la tarea.

Se excluyeron `.git/` de la copia de archivos y los recursos regenerables `venv`, `.venv`, `__pycache__`, cachés de herramientas y egg-info. El historial está protegido por los bundles. El entorno virtual no es un respaldo de dependencias instaladas: para restaurar otra máquina hay que recrearlo según pyproject.

La recuperación no se limitó a verificar un ZIP: `ScienceService` abrió el paquete **extraído** y confirmó integridad, cinco objetivos y una fila SPLICES, sin necesitar el caché original. Los hardlinks pasan a archivos independientes al archivarlos, por lo que no dependen del almacenamiento original.

Para recuperar sin tocar el proyecto actual: extraer el ZIP en un directorio nuevo y comparar con `backup-manifest.json`. Para recuperar el historial, crear otra copia desde el bundle con `git clone <bundle> <directorio-nuevo>`, y reponer los datos desde la extracción. No ejecutar restore/reset sobre el árbol actual como procedimiento de recuperación automático.

## 3. Commit B2 y referencia local de recuperación

Se mostró el alcance antes del commit y se comprobó el índice completo:

| Grupo | Archivos |
|---|---:|
| `app/b2/*.py` | 26 |
| `tests/` | 8 |
| Documentación/evidencias B2 en `docs/` | 9 |
| `pyproject.toml` | 1 |
| **Total** | **44** |

Commit de protección:

```text
86bc3f17cd5c04455b751933fc232cfa82e5d8eb
feat(b2): preserve science service and validated offline integration
```

Referencia persistente local, creada sin cambiar de rama:

```text
recovery/b2-phase5-pre-main-20261115 -> 86bc3f1
```

El commit incluye contratos, código, pruebas, documentos B2 y evidencias documentales JSON; no incluye cachés, FITS, resultados `.b2-runs/`, entornos, temporales ni imágenes científicas generadas. Las evidencias documentales conservan procedencia y cifras, no los píxeles de observaciones. `git diff --cached --check` pasó antes de crear el commit.

Git no tenía identidad configurada. El usuario indicó `FlavioC30 <flaviocesar640@gmail.com>`. Se utilizó únicamente `git -c user.name=FlavioC30 -c user.email=flaviocesar640@gmail.com ...` en los comandos que la requerían; no se cambió la configuración permanente local ni global.

## 4. Actualización remota y merge

Después de proteger B2 se ejecutó `git fetch origin --prune`. No hubo cambios adicionales respecto de la auditoría. `git ls-remote --symref origin HEAD` confirmó que `main` seguía siendo la principal:

```text
origin/main = dd8af7c822ea6e22b1c9a58543d7ab65c80d35ba
origin/feature/spectra = 38c3fe0285a2fbbf44966889ad3852aa6508026f
```

Se ejecutó merge con `--no-ff --no-commit` y la identidad temporal, dejando una pausa para pruebas. **No hubo conflictos**, entradas sin fusionar ni resoluciones manuales/automáticas de conflictos ambiguos. Tras aprobar las comprobaciones se creó:

```text
17c859d5cb943d1622735c4e71e1ae2b60df30ad
merge: integrate origin/main while preserving B2 science
```

Padres verificados:

- Primero: `86bc3f1`, la implementación B2 protegida.
- Segundo: `dd8af7c`, main remoto auditado.

`origin/main` es ancestro del merge. `origin/feature/spectra` **no** es ancestro de nuestra rama. No se usaron pull, rebase, reset, clean, stash ni cambio de rama.

Un primer comando de merge sin `-c` fue rechazado por Git antes de integrar archivos, porque también exige identidad con `--no-commit`. Se repitió con la identidad temporal ya autorizada. No fue un conflicto de contenido.

## 5. Archivos incorporados

El merge incorporó **291 archivos afectados: 289 agregados y dos modificados, ninguno eliminado**, con 24.240 líneas agregadas respecto del commit B2.

- Modificados: `.gitignore` y `README.md`.
- Nuevos: `CLAUDE.md`, `CONTRIBUTING.md`, `pipeline/`, `analysis/`, documentación del equipo y `public-data/`.
- Productos remotos: 242 WebP y manifests/análisis JSON para cinco objetivos y tres campos custom precalculados.
- `app/main.py` no cambió. `pyproject.toml` conserva las dependencias y configuración B2.

Los ocho commits incorporados son `6d82414`, `32af38e`, `47669c9`, `2d32ef2`, `e986ab4`, `1181a6c`, `6ec73ce` y `dd8af7c`. El inventario detallado figura en `B2_REPOSITORY_AUDIT.md` y se reproduce con:

```powershell
git diff --name-status 86bc3f1 17c859d
git log --oneline 86bc3f1..17c859d
```

Los WebP incorporados ya estaban versionados por el equipo; no se añadieron datos FITS locales ni productos nuevos de nuestras pruebas a los commits.

## 6. Preservación verificada

Se compararon los 417 archivos del respaldo con el árbol posterior al merge: **415 permanecen idénticos byte a byte**. Las únicas diferencias son `.gitignore` y `README.md`, correspondientes a main.

Esto incluye los 26 módulos B2, ocho archivos de pruebas, nueve documentos/evidencias, dependencias locales y todos los datos/resultados originales. Permanecen los 14 FITS originales y los 48 recursos del paquete offline, con sus hashes anteriores. No se sobrescribieron resultados para ejecutar la nueva demo.

Comprobaciones Git sin diferencias:

```powershell
git diff --exit-code origin/main -- pipeline analysis public-data app/main.py
git diff --exit-code recovery/b2-phase5-pre-main-20261115 -- app/b2 tests pyproject.toml
```

La primera confirma que los módulos/productos del equipo y endpoints existentes coinciden con main; la segunda, que B2 conserva lo protegido antes del merge.

## 7. Pruebas posteriores al merge

| Comprobación | Resultado |
|---|---|
| Pytest completo, con datos reales locales y dos consultas pequeñas NASA/IPAC | **128 passed, 2 skipped, 2 warnings**, 152,04 s |
| Comparación con línea base | Mismos 128 aprobados y dos omitidos; cero fallos/errores |
| Mypy | Sin errores en 26 módulos |
| Compilación Python | `compileall -q app pipeline analysis`, correcta |
| Dependencias instaladas | `pip check`: No broken requirements found |
| FastAPI | `/`, `/health`, `/docs`, `/openapi.json`: HTTP 200 |
| Contratos | 43 modelos B2 generan JSON Schema; resumen hace round-trip Pydantic/JSON |
| ScienceService sin red | Integridad válida, 48 recursos, 12 FITS, cinco objetivos y una candidata SPLICES |
| CLI demo + reproducción | Correcta: cinco objetivos recalculados, una medida comparada, ninguna discrepancia |
| Git | Sin conflictos; comprobaciones de whitespace e integridad de árboles correctas |

Las dos omisiones siguen siendo integraciones con una pareja FITS real de B1 ausente. Las dos advertencias son la deprecación Starlette/TestClient-httpx y la advertencia ERFA de la prueba sintética de movimiento propio sin distancia. No se ocultaron ni se cambiaron pruebas para obtener estos resultados.

Evidencias nuevas, todas fuera de los commits y sin reemplazar archivos anteriores:

```text
.b2-runs/phase5-sync-tests-20261115-0315.xml
.b2-runs/phase5-sync-20261115-0315/post-merge-checks.json
.b2-runs/phase5-sync-20261115-0315/sync-evidence.json
.b2-runs/phase5-sync-demo-20261115-0320.json
.b2-runs/phase5-sync-replay-20261115-0320/
```

SHA-256 del JUnit: `711dfd42d95136cf8316d32c15f60e4b2df29deebec8ab75338d3b335c7493e7`.

SHA-256 del resumen demo: `4a421829d15f832ba9cb4063e8f8aa28004a179ab4304c3e976d6c4ecaeb144f`.

La suite se ejecutó con las variables locales de B2_PHASE4 y `B2_LIVE_IRSA=1`, `B2_LIVE_SPLICES=1`. Estas pruebas consultan metadatos acotados; no descargaron observaciones nuevas. La prueba de demo real bloquea conexiones socket/httpx. La CLI independiente reutilizó los FITS existentes y generó solo resultados nuevos.

Incidencias del script auxiliar: el bloqueo global de sockets impidió crear el socketpair local de asyncio en Windows; otro intento confundió la instancia API con el paquete Python `app`. Se corrigieron únicamente los comandos de comprobación, no el proyecto. Finalmente la API se probó con sockets locales permitidos y ScienceService por separado con conexiones bloqueadas. No se atribuyen esos fallos del script a una regresión del backend. La demo conserva los avisos INFO de SIP de Astropy ya conocidos, sin modificar los FITS.

## 8. Dependencias y alcance de validación

No se instalaron paquetes ni se modificaron requirements del equipo. No se identificó incompatibilidad de rangos entre lo declarado por B2 y el remoto. Sin embargo, **faltan reproject, scipy, photutils, jsonschema y psutil** en el entorno actual. YAML, requests y Pillow sí están disponibles.

`pip check` valida los paquetes instalados; no prueba que estén instaladas todas las dependencias de los requirements adicionales. La compilación comprueba sintaxis, no imports de paquetes ausentes. Por tanto **no se declara ejecutable ni probado de extremo a extremo el pipeline B1/análisis remoto en este entorno**. Esta limitación ya existía en la auditoría y no afecta a los imports B2 ni a la API actual, que no importan esos módulos.

Además setuptools sigue incluyendo solo `app*`: distribuir `pipeline/` y `analysis/` como wheel requiere una decisión posterior. El entorno de datos del equipo debe validarse por separado, sin sustituir nuestro entorno comprobado durante esta sincronización.

## 9. Estado B1 y B3 después del merge

**B1:** código de consulta/descarga, reproyección, stacks, exportación y jobs custom incorporado sin alteraciones. Los manifests/WebP están presentes. Los FITS procesados siguen fuera de Git y no se entregó una pareja compatible. Faltan para nuestro adaptador metadatos temporales/detector en el HDU seleccionado, unidades correctas de varianza, máscaras y evidencias de banda efectiva/calibración/PSF/registro.

**B3:** API base preservada, con `/` y `/health`. No hay nuevos endpoints custom/ciencia ni importación de ScienceService. Las funciones B1 para jobs y la fachada B2 están disponibles para una conexión futura autorizada; sincronizar Git no realiza esa conexión.

No se certifican curvas completas, espectros completos ni diferencias temporales reales por esta fase. La medida local WISE 0855 sigue siendo preliminar, SNR ~1,157, sin detección. Los resultados más extensos publicados por el equipo son productos separados que requieren validación desde sus exposiciones.

## 10. Feature/spectra: comparación sin fusionar

Se inspeccionaron sus objetos Git, sin checkout ni ejecución. Contiene main más `76d73e6` y `38c3fe0`: 17 rutas diferentes, 14.869 líneas agregadas y 101 eliminadas respecto de main, principalmente datos JSON.

Aporta realmente:

- `analysis/spectra.py`: espectrofotometría por exposición, binning R~40/120, espectros por pasada/combinado, índices de cocientes y profundidades de absorción.
- `analysis/custom_spectrum.py`: consulta/fotometría/espectro para coordenadas arbitrarias y ubicación del objetivo en un campo visual.
- `analysis/splices.py`: consultas Gator, catálogo compacto de 2.293 candidatas y heurística de prioridad.
- Actualización de build, fotometría, esquema JSON y productos de los cinco objetivos; dos análisis custom, documentación y una figura.

| Aspecto | Nuestro B2 | Implementación remota |
|---|---|---|
| Contratos | Pydantic estricto, procedencia/estados/unidades explícitos | Diccionarios y JSON Schema; productos orientados a visualización |
| Fotometría | Rechazo de máscaras/ruido/fondo inválidos; estimaciones preliminares | Rellena huecos saturados como cotas inferiores y sustituye varianzas inválidas |
| Curvas | Compara respuestas compatibles sin inventar épocas | Ajusta forma espectral común multiplicada por factor temporal, piso sistemático 3% |
| Diferencias | Bloquea entradas incompatibles y exige evidencia | Resta por detector y después registra caveats; 44/64 productos avisan mismatch espectral |
| Espectros | Contratos y agrupación conservadores; datos locales insuficientes | Mayor cobertura publicada, índices/profundidades y umbral formal de significancia |
| SPLICES | Snapshot verificable, metadatos, consulta y source_id conservados | Catálogo amplio columns+rows y prioridad visual; pierde precisión/identidad en exportación |
| Servicio B3 | ScienceService y paquete verificable/offline | JSON/WebP precalculados; sin fachada conectada a FastAPI |

Duplicación: adquisición, fotometría, curvas, diferencias, espectros y catálogo. La rama aporta funcionalidad y más productos, pero no debe reemplazar B2 automáticamente. Sus índices espectrales y booleanos significant no equivalen por sí solos a detección molecular validada.

Problemas pendientes: propagación de incertidumbre del modelo espectral/temporal y de reproyección, saturación, respuesta/PSF entre pasadas, trazabilidad hasta FITS originales y tests. `analysis/splices.py` redondea todos los floats a tres decimales antes de exportar coordenadas a seis: las 2.293 posiciones publicadas conservan solo tres decimales de grado. El compacto omite source_id. Esto debe revisarse antes de usarlo en cruces astrométricos o reemplazar el snapshot local.

**Recomendación de canon, sin imponer cambios al equipo:** conservar `pipeline/` como productor B1; usar `app/b2/` como contrato científico y servicio público canónico por su tipado, controles y pruebas. Tratar los algoritmos/productos `analysis/` como aportes candidatos a incorporar mediante adaptadores y pruebas comparativas, preservando su autoría y procedencia. B3 debería delegar la ciencia en la fachada acordada, evitando dos motores con resultados contradictorios. La decisión organizativa final debe aprobarla el equipo; no se eliminó ni reemplazó código.

## 11. Riesgos y siguiente paso

1. Solicitar a B1 una pareja pequeña con FITS completos, máscaras/ruido, tiempos, procedencia, banda efectiva y evidencia de PSF/registro; verificarla antes de hacer diferencias.
2. Acordar canon y mapa de identificadores/unidades entre manifests y DTOs; no relajar validaciones para aceptar JSON remoto.
3. Preparar un entorno separado para dependencias B1/analysis y reproducir resultados reales; los actuales 128 tests no certifican ese código remoto.
4. Revisar feature/spectra y sus cuestiones científicas/astrométricas en otra tarea; no fusionarla hasta acordar contratos y pruebas.
5. Conectar B3 a ScienceService con rutas/errores HTTP revisados y servir solo productos inventariados, conservando advertencias de baja SNR y resultados bloqueados.

La sincronización solicitada está completada localmente y verificada. Los respaldos y la referencia de recuperación se conservan. No hubo push ni modificaciones adicionales al trabajo B1/B3. Publicar la rama o incorporar spectra requiere una instrucción posterior.
