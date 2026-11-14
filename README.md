# Ruta del Agua - Backend

Backend FastAPI para el desafío **Planet X SPHEREx**.

## Requisitos

- Python 3.11 o superior
- PowerShell

Verificar Python:

```powershell
python --version
```

## Instalación

Ejecutar desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Si PowerShell bloquea la activación:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Iniciar el backend

Con el entorno virtual activado:

```powershell
uvicorn app.main:app --reload
```

URLs:

- API: <http://127.0.0.1:8000>
- Documentación: <http://127.0.0.1:8000/docs>
- Salud: <http://127.0.0.1:8000/health>

Detener el servidor con `Ctrl+C`.

Salir del entorno virtual:

```powershell
deactivate
```
