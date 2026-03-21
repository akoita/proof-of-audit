from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from proof_of_audit_api.config import ContractConfig, DEFAULT_API_ENV_FILE, load_env_file
from proof_of_audit_api.publisher import (
    OnchainChallengeError,
    OnchainConfigurationError,
    OnchainPublishError,
    OnchainResolveError,
)
from proof_of_audit_api.schemas import (
    AuditListResponse,
    AuditRecordModel,
    AuditorRegistrationDocumentModel,
    AuditorReputationResponse,
    AuditorServiceListResponse,
    AuditorServiceRecordModel,
    ChallengeAuditRequest,
    ChallengerFeedResponse,
    CreateAuditRequest,
    DemoFixtureListResponse,
    ErrorResponse,
    HealthResponse,
    PublicContractConfigResponse,
    PublishAuditRequest,
    ResolveAuditRequest,
    TargetComparisonResponse,
    TargetAuditClaimsResponse,
    VerificationDossierModel,
)
from proof_of_audit_api.service import AuditService


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def create_app(
    data_root: Path | None = None,
    env_file: Path | None = DEFAULT_API_ENV_FILE,
    audit_service: AuditService | None = None,
) -> FastAPI:
    runtime_env = load_env_file(env_file or DEFAULT_API_ENV_FILE)
    runtime_env.update(os.environ)
    contract_config = ContractConfig.from_env(env_file=env_file)
    store_kind = runtime_env.get("PROOF_OF_AUDIT_STORE_KIND", "sqlite")
    store_path = runtime_env.get("PROOF_OF_AUDIT_STORE_PATH")
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
        store_kind=store_kind,
        store_path=Path(store_path) if store_path else None,
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
        service = _service(request)
        return PublicContractConfigResponse(
            network=contract_config.network,
            chain_id=contract_config.chain_id,
            contract_address=contract_config.contract_address,
            explorer_base_url=contract_config.explorer_base_url,
            arbiter=contract_config.arbiter,
            auditor=contract_config.auditor.to_dict(),
            auditor_service=service.get_auditor_service(
                contract_config.auditor_service.service_id
            )
            or contract_config.auditor_service.to_dict(),
            required_stake_wei=contract_config.required_stake_wei,
            required_challenge_bond_wei=contract_config.required_challenge_bond_wei,
            challenge_window_seconds=contract_config.challenge_window_seconds,
            deployment_ready=contract_config.deployment_ready,
        )

    @app.get("/auditor", response_model=AuditorServiceRecordModel)
    def auditor_service(request: Request) -> AuditorServiceRecordModel:
        service = _service(request)
        contract_config = request.app.state.contract_config
        payload = service.get_auditor_service(contract_config.auditor_service.service_id)
        return AuditorServiceRecordModel.model_validate(
            payload or contract_config.auditor_service.to_dict()
        )

    @app.get("/auditors", response_model=AuditorServiceListResponse)
    def auditor_services(request: Request) -> AuditorServiceListResponse:
        return AuditorServiceListResponse(
            items=[
                AuditorServiceRecordModel.model_validate(service)
                for service in _service(request).list_auditor_services()
            ]
        )

    @app.get(
        "/auditors/{service_id}",
        response_model=AuditorServiceRecordModel,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def auditor_service_detail(
        service_id: str, request: Request
    ) -> AuditorServiceRecordModel:
        payload = _service(request).get_auditor_service(service_id)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "auditor_not_found"},
            )
        return AuditorServiceRecordModel.model_validate(payload)

    @app.get("/auditor/registration", response_model=AuditorRegistrationDocumentModel)
    def auditor_registration(request: Request) -> AuditorRegistrationDocumentModel:
        contract_config = request.app.state.contract_config
        return AuditorRegistrationDocumentModel.model_validate(
            contract_config.auditor_registration_document()
        )

    @app.get(
        "/auditor/reputation",
        response_model=AuditorReputationResponse,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def auditor_reputation(request: Request) -> AuditorReputationResponse:
        service = _service(request)
        contract_config = request.app.state.contract_config
        payload = service.get_auditor_reputation(
            contract_config.auditor_service.service_id
        )
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "auditor_reputation_not_found"},
            )
        return AuditorReputationResponse.model_validate(payload)

    @app.get(
        "/auditors/{service_id}/registration",
        response_model=AuditorRegistrationDocumentModel,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def auditor_registration_detail(
        service_id: str, request: Request
    ) -> AuditorRegistrationDocumentModel:
        contract_config = request.app.state.contract_config
        payload = contract_config.auditor_registration_document_by_service_id(service_id)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "auditor_registration_not_found"},
            )
        return AuditorRegistrationDocumentModel.model_validate(payload)

    @app.get(
        "/auditors/{service_id}/reputation",
        response_model=AuditorReputationResponse,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def auditor_reputation_detail(
        service_id: str, request: Request
    ) -> AuditorReputationResponse:
        payload = _service(request).get_auditor_reputation(service_id)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "auditor_reputation_not_found"},
            )
        return AuditorReputationResponse.model_validate(payload)

    @app.get(
        "/audits",
        response_model=AuditListResponse,
        responses={status.HTTP_200_OK: {"model": AuditListResponse}},
    )
    def list_audits(
        request: Request,
        contract_address: str | None = Query(default=None),
    ) -> AuditListResponse:
        service = _service(request)
        return AuditListResponse(items=service.list_audits(contract_address=contract_address))

    @app.get(
        "/targets/{contract_address}/audits",
        response_model=TargetAuditClaimsResponse,
        responses={status.HTTP_200_OK: {"model": TargetAuditClaimsResponse}},
    )
    def list_target_audits(
        contract_address: str, request: Request
    ) -> TargetAuditClaimsResponse:
        service = _service(request)
        items = service.list_target_claims(contract_address)
        return TargetAuditClaimsResponse(
            target_contract=contract_address.lower(),
            target_key=contract_address.lower(),
            items=items,
        )

    @app.get(
        "/targets/{contract_address}/comparison",
        response_model=TargetComparisonResponse,
        responses={status.HTTP_200_OK: {"model": TargetComparisonResponse}},
    )
    def target_comparison(
        contract_address: str, request: Request
    ) -> TargetComparisonResponse:
        service = _service(request)
        return TargetComparisonResponse.model_validate(
            service.build_target_comparison(contract_address)
        )

    @app.get(
        "/challenger-feed",
        response_model=ChallengerFeedResponse,
        responses={status.HTTP_200_OK: {"model": ChallengerFeedResponse}},
    )
    def challenger_feed(
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> ChallengerFeedResponse:
        service = _service(request)
        return ChallengerFeedResponse(items=service.list_challenger_events(limit=limit))

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

    @app.get(
        "/audits/{audit_id}/challenge/dossier",
        response_model=VerificationDossierModel,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def get_challenge_verification_dossier(
        audit_id: str, request: Request
    ) -> VerificationDossierModel:
        service = _service(request)
        dossier = service.get_challenge_verification_dossier(audit_id)
        if dossier is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "challenge_verification_dossier_not_found"},
            )
        return VerificationDossierModel.model_validate(dossier)

    @app.get(
        "/audits/{audit_id}/validation/request",
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def get_validation_request_document(
        audit_id: str, request: Request
    ) -> dict[str, object]:
        service = _service(request)
        payload = service.get_validation_request_document(audit_id)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "validation_request_not_found"},
            )
        return payload

    @app.get(
        "/audits/{audit_id}/validation/response",
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def get_validation_response_document(
        audit_id: str, request: Request
    ) -> dict[str, object]:
        service = _service(request)
        payload = service.get_validation_response_document(audit_id)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "validation_response_not_found"},
            )
        return payload

    @app.get(
        "/audits/{audit_id}/reputation/claim",
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def get_reputation_claim_document(
        audit_id: str, request: Request
    ) -> dict[str, object]:
        service = _service(request)
        payload = service.get_reputation_claim_document(audit_id)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "reputation_claim_not_found"},
            )
        return payload

    @app.get(
        "/audits/{audit_id}/reputation/resolution",
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def get_reputation_resolution_document(
        audit_id: str, request: Request
    ) -> dict[str, object]:
        service = _service(request)
        payload = service.get_reputation_resolution_document(audit_id)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "reputation_resolution_not_found"},
            )
        return payload

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
                evidence_type=payload.evidence_type,
                execution_env=payload.execution_env,
                evidence_manifest=(
                    payload.evidence_manifest.model_dump(exclude_none=True)
                    if payload.evidence_manifest is not None
                    else None
                ),
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
