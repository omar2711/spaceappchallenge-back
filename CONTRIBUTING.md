# Cómo contribuir

1. **Ramas por persona o módulo.** Nunca trabajar directo en `main`.
   Ejemplos: `ana/frontend`, `modulo/datos`.
2. **Commits pequeños** y con mensajes claros (qué cambió y por qué).
3. **Merge a `main` cada 2–3 horas.** Antes de mergear, actualiza tu rama con `main` y verifica que nada se rompa.
4. **Nunca subir claves.** Las credenciales van en `.env` (ignorado por git). Documenta las variables necesarias en `.env.example` sin valores reales.
5. Los acuerdos importantes del equipo se anotan en [docs/decisiones.md](docs/decisiones.md).
6. **Hooks del repo:** actívalos una vez por clon con `git config core.hooksPath .githooks`. Mantienen los mensajes de commit limpios.
