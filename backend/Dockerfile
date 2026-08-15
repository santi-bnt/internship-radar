FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV XDG_CACHE_HOME=/var/cache/tectonic

WORKDIR /app
ARG TECTONIC_VERSION=0.17.0
COPY tectonic-smoke.tex /tmp/tectonic-smoke.tex
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl fontconfig fonts-dejavu-core fonts-lmodern \
    && curl -fsSL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
      | tar -xz -C /usr/local/bin tectonic \
    && tectonic --version \
    && fc-cache -f \
    && mkdir -p "${XDG_CACHE_HOME}" \
    && tectonic --outdir /tmp /tmp/tectonic-smoke.tex \
    && rm -f /tmp/tectonic-smoke.tex /tmp/tectonic-smoke.pdf \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
COPY alembic ./alembic
COPY alembic.ini .
RUN useradd --create-home --uid 10001 radar \
    && chown -R radar:radar /app \
    && chown -R radar:radar /var/cache/tectonic

USER radar

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/health', timeout=8)"
CMD ["sh", "-c", "python -m app.jobs.prepare_database && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
