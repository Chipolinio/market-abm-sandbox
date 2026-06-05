# Backend runtime image (Spec 007 §7.3).
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml specs/001-synthetic-population.md ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN useradd --uid 1000 --create-home appuser \
    && mkdir -p /data/runs \
    && chown -R appuser:appuser /data/runs

USER appuser

ENV SIMULATION_ARTIFACTS_DIR=/data/runs/default
VOLUME /data/runs
EXPOSE 8000

CMD ["uvicorn", "market_abm.main:app", "--host", "0.0.0.0", "--port", "8000"]
