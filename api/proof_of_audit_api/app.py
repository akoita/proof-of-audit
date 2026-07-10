from __future__ import annotations

import base64
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
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
    OnchainRequestError,
    OnchainResolveError,
)
from proof_of_audit_api.schemas import (
    AuditListResponse,
    AuditRequestEligibilityResponse,
    AuditRequestClaimListResponse,
    AuditRequestListResponse,
    AuditRequestRecordModel,
    AuditRecordModel,
    AuditorRegistrationDocumentModel,
    AuditorReputationResponse,
    AuditorServiceListResponse,
    AuditorServiceRecordModel,
    ChallengeAuditRequest,
    ChallengerFeedResponse,
    CreateAuditMarketplaceRequest,
    CreateAuditRequest,
    DemoFixtureListResponse,
    ErrorResponse,
    HealthResponse,
    MarketplacePreviewRequest,
    MarketplacePreviewResponse,
    PublicContractConfigResponse,
    PublishAuditRequest,
    ResolveAuditRequest,
    RuntimeDiagnosticsResponse,
    SourceBundleUploadRequest,
    SourceBundleUploadResponse,
    SubmitAuditRequestClaimRequest,
    TargetComparisonResponse,
    TargetAuditClaimsResponse,
    VerificationDossierModel,
)
from proof_of_audit_api.security import build_mutating_guard
from proof_of_audit_api.service import AuditService
from proof_of_audit_api.source_bundle_storage import (
    SourceBundleStorageError,
    build_source_bundle_storage,
    validate_upload_filename,
)
from proof_of_audit_api.store import CloudSqlPostgresConfig


logger = logging.getLogger(__name__)

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


def _enforce_key_separation(contract_config: ContractConfig) -> None:
    """Refuse to start when trust roles share signing keys on a real network.

    The publisher, arbiter, validator and reputation-operator must be distinct
    addresses: the party staking behind verdicts must not be the party
    resolving disputes. On local development networks a single shared key is
    tolerated (with a loud warning); everywhere else it is a fatal
    misconfiguration.
    """
    violations = contract_config.key_separation_violations()
    if not violations:
        return
    if contract_config.is_local_network():
        logger.warning(
            "Trust roles share signing addresses on local network %r: %s. "
            "Single-key mode is acceptable ONLY for local development; set "
            "distinct role keys before deploying to a real network.",
            contract_config.network,
            "; ".join(violations),
        )
        return
    raise RuntimeError(
        "Key role separation violated on network "
        f"{contract_config.network!r}: "
        + "; ".join(violations)
        + ". The publisher, arbiter, validator and reputation-operator must be "
        "distinct addresses. Set PROOF_OF_AUDIT_ARBITER_PRIVATE_KEY, "
        "PROOF_OF_AUDIT_VALIDATOR_PRIVATE_KEY and "
        "PROOF_OF_AUDIT_REPUTATION_OPERATOR_PRIVATE_KEY to keys distinct from "
        "the publisher key (PROOF_OF_AUDIT_PRIVATE_KEY)."
    )


def _enforce_api_security(contract_config: ContractConfig) -> None:
    """Refuse to start with an unauthenticated / wide-open API on a real network.

    Mutating endpoints must be gated behind an API key and CORS must name
    explicit origins on any non-local network. On local development networks an
    open API is tolerated (with a loud warning); everywhere else it is a fatal
    misconfiguration.
    """
    if contract_config.is_local_network():
        if not contract_config.api_keys:
            logger.warning(
                "Proof-of-Audit API is running WITHOUT API-key authentication on "
                "local network %r: all mutating endpoints are OPEN. This is "
                "acceptable ONLY for local development; set "
                "PROOF_OF_AUDIT_API_KEYS before deploying to a real network.",
                contract_config.network,
            )
        return
    if not contract_config.api_keys:
        raise RuntimeError(
            "API-key authentication is required on network "
            f"{contract_config.network!r} but PROOF_OF_AUDIT_API_KEYS is empty. "
            "Set PROOF_OF_AUDIT_API_KEYS to a comma-separated list of secret "
            "keys so mutating endpoints reject unauthenticated callers."
        )
    if "*" in contract_config.cors_allow_origins:
        raise RuntimeError(
            "Wildcard CORS origin '*' is not allowed on network "
            f"{contract_config.network!r}. Set PROOF_OF_AUDIT_CORS_ALLOW_ORIGINS "
            "to an explicit comma-separated list of allowed origins."
        )


def create_app(
    data_root: Path | None = None,
    env_file: Path | None = DEFAULT_API_ENV_FILE,
    audit_service: AuditService | None = None,
) -> FastAPI:
    runtime_env = load_env_file(env_file or DEFAULT_API_ENV_FILE)
    runtime_env.update(os.environ)
    contract_config = ContractConfig.from_env(env_file=env_file)
    store_kind = runtime_env.get("PROOF_OF_AUDIT_STORE_KIND", "sqlite")
    normalized_store_kind = store_kind.strip().lower() if store_kind else "sqlite"
    store_path_value = runtime_env.get("PROOF_OF_AUDIT_STORE_PATH")
    store_path = (
        Path(store_path_value)
        if store_path_value and normalized_store_kind != "cloudsql-postgres"
        else None
    )
    postgres_config = (
        CloudSqlPostgresConfig.from_env(runtime_env)
        if normalized_store_kind == "cloudsql-postgres"
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            app.state.audit_service.close()

    app = FastAPI(
        title="Proof-of-Audit API",
        version="0.2.0",
        description="API for creating, publishing, and challenging audit records.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(contract_config.cors_allow_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.audit_service = audit_service or AuditService(
        data_root or Path(os.environ.get("PROOF_OF_AUDIT_DATA_ROOT", DATA_ROOT)),
        contract_config=contract_config,
        store_kind=store_kind,
        store_path=store_path,
        postgres_config=postgres_config,
    )
    if audit_service is not None:
        contract_config = audit_service.contract_config
    app.state.contract_config = contract_config

    _enforce_key_separation(contract_config)
    _enforce_api_security(contract_config)
    mutating_guard = build_mutating_guard(contract_config)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        del request
        if isinstance(exc.detail, dict):
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=exc.headers,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "http_error", "message": str(exc.detail)},
            headers=exc.headers,
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

    @app.get("/diagnostics/runtime", response_model=RuntimeDiagnosticsResponse)
    def runtime_diagnostics(request: Request) -> RuntimeDiagnosticsResponse:
        return RuntimeDiagnosticsResponse.model_validate(
            _service(request).runtime_diagnostics()
        )

    @app.get("/config", response_model=PublicContractConfigResponse)
    def config(request: Request) -> PublicContractConfigResponse:
        contract_config = request.app.state.contract_config
        service = _service(request)
        public_api_base_url = _public_api_base_url(request)
        fee_config = None
        if service.publisher is not None:
            try:
                fee_config = service.publisher.get_marketplace_fee_config()
            except Exception:
                fee_config = None
        return PublicContractConfigResponse(
            network=contract_config.network,
            chain_id=contract_config.chain_id,
            contract_address=contract_config.contract_address,
            explorer_base_url=contract_config.explorer_base_url,
            arbiter=contract_config.arbiter,
            treasury_address=(
                fee_config.treasury_address
                if fee_config is not None
                else contract_config.treasury_address
            ),
            auditor=contract_config.auditor_public_profile(
                api_base_url=public_api_base_url
            ),
            auditor_service=service.get_auditor_service(
                contract_config.auditor_service.service_id
            )
            or contract_config.auditor_service.to_dict(),
            required_stake_wei=contract_config.required_stake_wei,
            required_challenge_bond_wei=contract_config.required_challenge_bond_wei,
            challenge_window_seconds=contract_config.challenge_window_seconds,
            fee_denominator=(
                fee_config.fee_denominator if fee_config is not None else 10_000
            ),
            protocol_fee_bps=(
                fee_config.protocol_fee_bps
                if fee_config is not None
                else contract_config.protocol_fee_bps
            ),
            resolution_fee_bps=(
                fee_config.resolution_fee_bps
                if fee_config is not None
                else contract_config.resolution_fee_bps
            ),
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
            contract_config.auditor_registration_document(
                api_base_url=_public_api_base_url(request)
            )
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
        if service_id == contract_config.auditor_service.service_id:
            payload = contract_config.auditor_registration_document(
                api_base_url=_public_api_base_url(request)
            )
        else:
            payload = contract_config.auditor_registration_document_by_service_id(
                service_id
            )
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
        "/requests",
        response_model=AuditRequestListResponse,
        responses={status.HTTP_200_OK: {"model": AuditRequestListResponse}},
    )
    def list_requests(
        request: Request,
        status_filter: str | None = Query(default=None, alias="status"),
    ) -> AuditRequestListResponse:
        service = _service(request)
        return AuditRequestListResponse(
            items=service.list_audit_requests(status=status_filter)
        )

    @app.post(
        "/requests",
        response_model=AuditRequestRecordModel,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(mutating_guard)],
        responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
            status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        },
    )
    def create_request(
        payload: CreateAuditMarketplaceRequest,
        request: Request,
    ) -> AuditRequestRecordModel:
        service = _service(request)
        try:
            record = service.create_audit_request(
                contract_address=payload.contract_address,
                bounty_wei=payload.bounty_wei,
                response_window_seconds=payload.response_window_seconds,
                filters=payload.filters.model_dump(),
            )
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
        except OnchainRequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "request_create_failed", "message": str(exc)},
            ) from exc
        return AuditRequestRecordModel.model_validate(record)

    @app.get(
        "/requests/{request_id}",
        response_model=AuditRequestRecordModel,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def get_request(request_id: str, request: Request) -> AuditRequestRecordModel:
        service = _service(request)
        payload = service.get_audit_request(request_id)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "request_not_found"},
            )
        return AuditRequestRecordModel.model_validate(payload)

    @app.get(
        "/requests/{request_id}/claims",
        response_model=AuditRequestClaimListResponse,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def list_request_claims(
        request_id: str,
        request: Request,
    ) -> AuditRequestClaimListResponse:
        service = _service(request)
        try:
            items = service.list_audit_request_claims(request_id)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "request_not_found"},
            ) from None
        return AuditRequestClaimListResponse(items=items)

    @app.post(
        "/requests/{request_id}/claims",
        response_model=AuditRecordModel,
        dependencies=[Depends(mutating_guard)],
        responses={
            status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
            status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        },
    )
    def submit_request_claim(
        request_id: str,
        payload: SubmitAuditRequestClaimRequest,
        request: Request,
    ) -> AuditRecordModel:
        service = _service(request)
        try:
            record = service.submit_audit_request_claim(
                request_id,
                audit_id=payload.audit_id,
                stake_wei=payload.stake_wei,
                challenge_policy=payload.challenge_policy.model_dump(),
            )
        except KeyError as exc:
            missing_key = str(exc.args[0]) if exc.args else ""
            error_name = "request_not_found" if missing_key == request_id else "audit_not_found"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": error_name},
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
        except OnchainRequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "request_claim_failed", "message": str(exc)},
            ) from exc
        return AuditRecordModel.model_validate(record)

    @app.get(
        "/requests/{request_id}/eligibility",
        response_model=AuditRequestEligibilityResponse,
        responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    )
    def request_eligibility(
        request_id: str,
        request: Request,
        auditor: str = Query(..., min_length=1),
    ) -> AuditRequestEligibilityResponse:
        service = _service(request)
        payload = service.build_audit_request_eligibility(request_id, auditor)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "request_not_found"},
            )
        return AuditRequestEligibilityResponse.model_validate(payload)

    @app.post(
        "/marketplace/preview",
        response_model=MarketplacePreviewResponse,
        dependencies=[Depends(mutating_guard)],
        responses={status.HTTP_200_OK: {"model": MarketplacePreviewResponse}},
    )
    def marketplace_preview(
        payload: MarketplacePreviewRequest,
        request: Request,
    ) -> MarketplacePreviewResponse:
        service = _service(request)
        return MarketplacePreviewResponse.model_validate(
            service.build_marketplace_preview(payload.model_dump())
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

    @app.post(
        "/source-bundles/upload",
        response_model=SourceBundleUploadResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(mutating_guard)],
        responses={status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}},
    )
    async def upload_source_bundle(
        request: Request,
        payload: SourceBundleUploadRequest,
    ) -> SourceBundleUploadResponse:
        try:
            original_name = validate_upload_filename(payload.filename)
            service = _service(request)
            storage = build_source_bundle_storage(
                workspace_root=service.worker.workspace_root,
                env=runtime_env,
            )
            stored_bundle = storage.store(
                original_filename=original_name,
                content=base64.b64decode(payload.content_base64),
            )
        except SourceBundleStorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_upload",
                    "message": str(exc),
                },
            ) from exc

        return SourceBundleUploadResponse(
            original_filename=stored_bundle.original_filename,
            source_bundle_uri=stored_bundle.source_bundle_uri,
            storage_backend=stored_bundle.storage_backend,
            source_bundle_label=stored_bundle.source_bundle_label,
            entry_contract=stored_bundle.entry_contract,
        )

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
        dependencies=[Depends(mutating_guard)],
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
        dependencies=[Depends(mutating_guard)],
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
                challenge_policy=payload.challenge_policy.model_dump(),
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
        dependencies=[Depends(mutating_guard)],
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
        dependencies=[Depends(mutating_guard)],
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


def _public_api_base_url(request: Request) -> str:
    contract_config = request.app.state.contract_config
    return contract_config.public_api_base_url(str(request.base_url)) or str(
        request.base_url
    ).rstrip("/")


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
