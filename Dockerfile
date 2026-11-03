FROM python:3.10-slim

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    BIOFORGE_HOST=0.0.0.0 \
    BIOFORGE_PORT=8010

WORKDIR /app
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then sed -i "s|http://deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; fi \
    && if [ -f /etc/apt/sources.list ]; then sed -i "s|http://deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list; fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libxrender1 libxext6 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

COPY backend ./backend
COPY data ./data
COPY web ./web
COPY scripts ./scripts
COPY docs ./docs
COPY README.md CHANGELOG.md RELEASES.md ./
COPY tests ./tests

RUN mkdir -p /app/runtime /app/logs
EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/api/health', timeout=4).read()"

CMD ["python", "-m", "uvicorn", "backend.app_v3:app", "--host", "0.0.0.0", "--port", "8010", "--proxy-headers", "--forwarded-allow-ips=*"]
