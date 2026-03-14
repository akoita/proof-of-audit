from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from proof_of_audit_api.config import ContractConfig, DEFAULT_API_ENV_FILE
from proof_of_audit_api.publisher import (
    OnchainChallengeError,
    OnchainConfigurationError,
    OnchainPublishError,
    OnchainResolveError,
)
from proof_of_audit_api.schemas import (
    AuditListResponse,
    AuditRecordModel,
    AuditorServiceRecordModel,
    ChallengeAuditRequest,
    CreateAuditRequest,
    DemoFixtureListResponse,
    ErrorResponse,
    HealthResponse,
    PublicContractConfigResponse,
    PublishAuditRequest,
    ResolveAuditRequest,
)
from proof_of_audit_api.service import AuditService


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def create_app(
    data_root: Path | None = None,
    env_file: Path | None = DEFAULT_API_ENV_FILE,
    audit_service: AuditService | None = None,
) -> FastAPI:
    contract_config = ContractConfig.from_env(env_file=env_file)
    app = FastAPI(
        title="Proof-of-Audit API",
        version="0.2.0",
        description="API for creating, publishing, and challenging audit records.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.audit_service = audit_service or AuditService(
        data_root or Path(os.environ.get("PROOF_OF_AUDIT_DATA_ROOT", DATA_ROOT)),
        contract_config=contract_config,
    )
    if audit_service is not None:
        contract_config = audit_service.contract_config
    app.state.contract_config = contract_config

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        del request
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "http_error", "message": str(exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "validation_error",
                "detail": jsonable_encoder(exc.errors()),
            },
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/config", response_model=PublicContractConfigResponse)
    def config(request: Request) -> PublicContractConfigResponse:
        contract_config = request.app.state.contract_config
        return PublicContractConfigResponse(
            network=contract_config.network,
            chain_id=contract_config.chain_id,
            contract_address=contract_config.contract_address,
            explorer_base_url=contract_config.explorer_base_url,
            arbiter=contract_config.arbiter,
            auditor=contract_config.auditor.to_dict(),
            auditor_service=contract_config.auditor_service.to_dict(),
            required_stake_wei=contract_config.required_stake_wei,
            required_challenge_bond_wei=contract_config.required_challenge_bond_wei,
            challenge_window_seconds=contract_config.challenge_window_seconds,
            deployment_ready=contract_config.deployment_ready,
        )

    @app.get("/auditor", response_model=AuditorServiceRecordModel)
    def auditor_service(request: Request) -> AuditorServiceRecordModel:
        contract_config = request.app.state.contract_config
        return AuditorServiceRecordModel.model_validate(
            contract_config.auditor_service.to_dict()
        )

    @app.get(
        "/audits",
        response_model=AuditListResponse,
        responses={status.HTTP_200_OK: {"model": AuditListResponse}},
    )
    def list_audits(request: Request) -> AuditListResponse:
        service = _service(request)
        return AuditListResponse(items=service.list_audits())

    @app.get(
        "/fixtures",
        response_model=DemoFixtureListResponse,
        responses={status.HTTP_200_OK: {"model": DemoFixtureListResponse}},
    )
    def list_demo_fixtures(request: Request) -> DemoFixtureListResponse:
        service = _service(request)
        return DemoFixtureListResponse(items=service.list_demo_fixtures())

    @app.get(
        "/audits/{audit_id}",
        response_model=AuditRecordModel,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def get_audit(audit_id: str, request: Request) -> AuditRecordModel:
        service = _service(request)
        record = service.get_audit(audit_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "audit_not_found"},
            )
        return AuditRecordModel.model_validate(record)

    @app.post(
        "/audits",
        response_model=AuditRecordModel,
        status_code=status.HTTP_201_CREATED,
    )
    def create_audit(
        payload: CreateAuditRequest, request: Request
    ) -> AuditRecordModel:
        service = _service(request)
        try:
            record = service.create_audit_submission(
                payload.model_dump(exclude={"submitted_by"}),
                submitted_by=payload.submitted_by,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_payload", "message": str(exc)},
            ) from exc
        return AuditRecordModel.model_validate(record)

    @app.post(
        "/audits/{audit_id}/publish",
        response_model=AuditRecordModel,
        responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
            status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        },
    )
    def publish_audit(
        audit_id: str, payload: PublishAuditRequest, request: Request
    ) -> AuditRecordModel:
        service = _service(request)
        try:
            record = service.publish_audit(
                audit_id,
                stake_wei=payload.stake_wei,
                agent_identity=payload.agent_identity,
            )
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "audit_not_found"},
            ) from None
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_payload", "message": str(exc)},
            ) from exc
        except OnchainConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "onchain_not_configured", "message": str(exc)},
            ) from exc
        except OnchainPublishError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "publish_failed", "message": str(exc)},
            ) from exc
        return AuditRecordModel.model_validate(record)

    @app.post(
        "/audits/{audit_id}/challenge",
        response_model=AuditRecordModel,
        responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
            status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        },
    )
    def challenge_audit(
        audit_id: str, payload: ChallengeAuditRequest, request: Request
    ) -> AuditRecordModel:
        service = _service(request)
        try:
            record = service.challenge_audit(
                audit_id,
                proof_uri=payload.proof_uri,
                challenger=payload.challenger,
            )
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "audit_not_found"},
            ) from None
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_payload", "message": str(exc)},
            ) from exc
        except OnchainConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "onchain_not_configured", "message": str(exc)},
            ) from exc
        except OnchainChallengeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "challenge_failed", "message": str(exc)},
            ) from exc
        return AuditRecordModel.model_validate(record)

    @app.post(
        "/audits/{audit_id}/resolve",
        response_model=AuditRecordModel,
        responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
            status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        },
    )
    def resolve_audit(
        audit_id: str, payload: ResolveAuditRequest, request: Request
    ) -> AuditRecordModel:
        service = _service(request)
        try:
            record = service.resolve_audit(
                audit_id,
                upheld=payload.upheld,
                resolved_by=payload.resolved_by,
            )
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "audit_not_found"},
            ) from None
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_payload", "message": str(exc)},
            ) from exc
        except OnchainConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "onchain_not_configured", "message": str(exc)},
            ) from exc
        except OnchainResolveError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "resolve_failed", "message": str(exc)},
            ) from exc
        return AuditRecordModel.model_validate(record)

    return app


def _service(request: Request) -> AuditService:
    return request.app.state.audit_service


def main() -> None:
    host = os.environ.get("PROOF_OF_AUDIT_HOST", "127.0.0.1")
    port = int(os.environ.get("PROOF_OF_AUDIT_PORT", "8080"))
    uvicorn.run(
        "proof_of_audit_api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
