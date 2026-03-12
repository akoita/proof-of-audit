from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from proof_of_audit_api.schemas import (
    AuditListResponse,
    AuditRecordModel,
    ChallengeAuditRequest,
    CreateAuditRequest,
    ErrorResponse,
    HealthResponse,
    PublishAuditRequest,
)
from proof_of_audit_api.service import AuditService


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def create_app(data_root: Path | None = None) -> FastAPI:
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
    app.state.audit_service = AuditService(data_root or DATA_ROOT)

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
            content={"error": "validation_error", "detail": exc.errors()},
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/audits",
        response_model=AuditListResponse,
        responses={status.HTTP_200_OK: {"model": AuditListResponse}},
    )
    def list_audits(request: Request) -> AuditListResponse:
        service = _service(request)
        return AuditListResponse(items=service.list_audits())

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
        record = service.create_audit(
            payload.contract_address, submitted_by=payload.submitted_by
        )
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
