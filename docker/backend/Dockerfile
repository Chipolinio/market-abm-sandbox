# Backend runtime image (Spec 007 §7.3).
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml specs/001-synthetic-population.md ./
COPY src ./src
COPY experiments ./experiments

RUN pip install --no-cache-dir .

RUN useradd --uid 1000 --create-home appuser \
    && mkdir -p /data/runs /data/experiments /data/ml_frozen \
    && chown -R appuser:appuser /data

USER appuser

ENV SIMULATION_ARTIFACTS_DIR=/data/runs/default
ENV EXPERIMENTS_DIR=/data/experiments
ENV MARKET_ABM_ML_FROZEN_DIR=/data/ml_frozen
VOLUME /data/runs
VOLUME /data/experiments
EXPOSE 8000

CMD ["uvicorn", "market_abm.main:app", "--host", "0.0.0.0", "--port", "8000"]
