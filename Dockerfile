# Backend runtime image: installs the package non-root and serves the FastAPI.
# When a frontend build exists at frontend/dist the app also serves the SPA
# (see docker-compose which mounts the built assets into the image).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY eval ./eval

# Install runtime dependencies first for better layer caching.
RUN pip install --no-cache-dir -e .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

CMD ["uvicorn", "foodarena_ai.main:app", "--host", "0.0.0.0", "--port", "8000"]
