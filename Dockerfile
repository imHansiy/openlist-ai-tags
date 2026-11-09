FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AI_DATA_DIR=/data AI_PROXY_ENABLED=false
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates tesseract-ocr tesseract-ocr-chi-sim && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 aitags && useradd -u 10001 -g aitags -m aitags && mkdir /data && chown aitags:aitags /data
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY aitags ./aitags
RUN pip install --no-cache-dir .
USER aitags
VOLUME /data
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/ai/health',timeout=3)"
CMD ["uvicorn", "aitags.app:app", "--host", "0.0.0.0", "--port", "8787", "--workers", "1", "--no-access-log"]
