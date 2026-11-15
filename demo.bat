@echo off
rem Modo demo local sin internet: levanta la API en http://localhost:8000
cd /d "%~dp0"
.venv\Scripts\python -m app.demo %*
