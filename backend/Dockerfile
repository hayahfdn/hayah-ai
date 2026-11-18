FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# FFmpeg is needed from Phase 7 (video). Build with --build-arg INSTALL_FFMPEG=false to skip it.
ARG INSTALL_FFMPEG=true
RUN if [ "$INSTALL_FFMPEG" = "true" ]; then apt-get update && apt-get install -y --no-install-recommends ffmpeg \
      && rm -rf /var/lib/apt/lists/*; fi \
    && useradd --create-home --uid 1000 hayah
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data /app/secrets && chown -R hayah:hayah /app/data
USER hayah
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
