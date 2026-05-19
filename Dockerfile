FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    PVESS_WEB_WORKDIR=/data/pvess-web \
    PORT=8765

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip

COPY . .
RUN python -m pip install --no-cache-dir .

RUN useradd --create-home --shell /usr/sbin/nologin pvess \
    && mkdir -p /data/pvess-web \
    && chown -R pvess:pvess /data/pvess-web

USER pvess
VOLUME ["/data/pvess-web"]
EXPOSE 8765

CMD ["sh", "-c", "uvicorn pvess_calc.web.server:app --host 0.0.0.0 --port ${PORT}"]
