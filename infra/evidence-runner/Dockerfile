FROM ghcr.io/foundry-rs/foundry:v1.3.1 AS foundry

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=foundry /usr/local/bin/forge /usr/local/bin/forge
COPY infra/evidence-runner/server.py /app/server.py

EXPOSE 8080

CMD ["python", "/app/server.py"]
