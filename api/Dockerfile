FROM ghcr.io/foundry-rs/foundry:v1.3.1 AS contracts-build

USER root

WORKDIR /src

COPY contracts /src/contracts

RUN forge build --root /src/contracts

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PROOF_OF_AUDIT_HOST=0.0.0.0
ENV PROOF_OF_AUDIT_PORT=8080

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

COPY pyproject.toml README.md LICENSE /app/
COPY agent /app/agent
COPY api /app/api
COPY deployments /app/deployments
COPY docs/registrations /app/docs/registrations
COPY --from=contracts-build /src/contracts/out/ProofOfAudit.sol/ProofOfAudit.json /app/contracts/out/ProofOfAudit.sol/ProofOfAudit.json

RUN mkdir -p /app/api/data /app/contracts/out/ProofOfAudit.sol \
    && python -m pip install --no-cache-dir --no-build-isolation .

EXPOSE 8080

CMD ["python", "-m", "proof_of_audit_api.app"]
