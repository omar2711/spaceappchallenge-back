# Ruta del Agua API (FastAPI + SPHEREx pipeline/analysis + B3).
# Heavy data that is not in git (prepared fields for /spectrum, ephemerides) is downloaded at build time
# from a GitHub release asset made with `python tools/data_bundle.py make` (see docs/DEPLOY.md).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /srv

# Dependencies first (cached layer). Editable install so app/ keeps resolving the repo root (/srv).
COPY pyproject.toml README.md ./
COPY tools/constraints.txt tools/constraints.txt
COPY app ./app
RUN pip install -c tools/constraints.txt -e ".[spherex]"

COPY . .

ARG DATA_BUNDLE_URL=https://github.com/omar2711/spaceappchallenge-back/releases/download/data-v1/data-bundle.tar.gz
RUN python tools/data_bundle.py fetch "$DATA_BUNDLE_URL" \
    && python -c "import app.main"

EXPOSE 8000
# Render (and most hosts) inject $PORT.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
