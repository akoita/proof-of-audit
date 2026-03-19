FROM ghcr.io/foundry-rs/foundry:v1.3.1 AS foundry

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/agent

WORKDIR /app

RUN python -m pip install --no-cache-dir google-cloud-storage==2.19.0

COPY agent /app/agent
COPY --from=foundry /usr/local/bin/forge /usr/local/bin/forge
COPY infra/evidence-runner/server.py /app/server.py

EXPOSE 8080

CMD ["python", "/app/server.py"]
