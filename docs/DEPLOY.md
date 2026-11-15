# Despliegue público de la API (Render, plan gratuito)

- **Imagen:** Docker (`Dockerfile`), con las mismas versiones que se probaron en local (`tools/constraints.txt`).
- **Datos pesados:** no están en git. Se bajan durante el build desde un *release* de GitHub (`data-bundle.tar.gz`, ~50 MB): los campos preparados para `/spectrum` y las efemerides.
- **Redespliegue:** automático en cada push a `main` (`render.yaml`, `autoDeploy: true`).
- **Salida a internet:** Render la permite, y `/custom` la necesita para llegar a IRSA.

## Pasos (una vez)

### 1. Publicar el paquete de datos como release de GitHub

1. Genera el paquete (o usa el que ya está en `dist/`):
   ```
   .venv\Scripts\python tools\data_bundle.py make
   ```
   Crea `dist/data-bundle.tar.gz`, de ~50 MB.
2. Entra a https://github.com/omar2711/spaceappchallenge-back/releases/new.
3. En **Choose a tag**, escribe `data-v1` y elige **Create new tag on publish**. El target es `main`.
4. Como título pon `Data bundle v1`. Arrastra `dist/data-bundle.tar.gz` a **Attach binaries**.
5. Pulsa **Publish release**.
6. Verifica que esta URL descarga el archivo (es la que usa el `Dockerfile`):
   `https://github.com/omar2711/spaceappchallenge-back/releases/download/data-v1/data-bundle.tar.gz`

### 2. Crear el servicio en Render

1. Crea una cuenta en https://render.com, con **Sign up with GitHub**.
2. Ve a **New → Blueprint** y conecta GitHub.
   - Render pide instalar su GitHub App en el repo. **Como el repo es de Omar, la instalación tiene que aprobarla Omar**: GitHub le envía la solicitud, o la hace él directamente.
3. Elige `omar2711/spaceappchallenge-back`. Render lee `render.yaml`, que crea el servicio web `ruta-del-agua-api` (Docker, free, rama `main`, autodeploy, health check `/health`).
4. Pulsa **Apply**. El primer build tarda ~5–10 minutos (dependencias científicas y paquete de datos).
5. La URL queda como `https://ruta-del-agua-api.onrender.com`; puede tener un sufijo si el nombre está ocupado. Pásamela.

No hace falta configurar variables de entorno.

**Si Omar no puede aprobar la app a tiempo**, hay una alternativa sin redespliegue automático:
1. Ve a **New → Web Service → Public Git Repository**, con la URL `https://github.com/omar2711/spaceappchallenge-back`, rama `main`, runtime Docker y plan Free.
2. Para redesplegar, usa **Manual Deploy → Deploy latest commit** después de cada push.

### 3. (Opcional) Mantenerlo despierto durante el evento

El plan gratuito **se duerme tras 15 minutos sin tráfico**, y la primera petición después tarda ~30–60 s.

- **Antes de presentar:** abre `https://<tu-url>/health` 2–3 minutos antes y espera a que responda `{"status":"ok"}`.
- **Despertador automático:**
  - En GitHub, entra a **Settings → Secrets and variables → Actions → Variables** y crea `API_URL` = `https://<tu-url>`. Esto requiere permisos de administración del repo (Omar).
  - Con eso se activa `.github/workflows/keepalive.yml`, que llama a `/health` cada 10 minutos.
  - Las 750 horas gratuitas al mes alcanzan para un servicio encendido todo el tiempo.
  - Para apagarlo, borra la variable.
- **Sin acceso de administrador:** cron-job.org (gratis), con un GET a `/health` cada 10 minutos.

## Actualizar los datos

- **Cambian los campos preparados o las efemérides:** regenera el paquete, publícalo como `data-v2` y actualiza el `ARG DATA_BUNDLE_URL` del `Dockerfile`.
- **Cambia `public-data/`:** va en git y se despliega solo con el push a `main`.

## Límites del plan gratuito

| Límite | Efecto |
|---|---|
| 512 MB de RAM | La API usa ~200 MB en reposo y un campo nuevo de `/custom` suma ~140 MB. Se procesa un trabajo a la vez |
| Disco efímero | Los campos que se generen con `/custom` se pierden en cada redespliegue o reinicio. Los presets y los 5 objetivos vienen en la imagen |
| CPU compartida | `/custom` puede tardar más que en local (~3–5 min por campo) |
