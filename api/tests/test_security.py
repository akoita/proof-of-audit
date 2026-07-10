"""Unit tests for the mutating-endpoint auth + rate-limit guard."""

import unittest
from types import SimpleNamespace

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from proof_of_audit_api.security import build_mutating_guard


def _config(
    api_keys=(),
    rate_limit=0,
    cors=("*",),
) -> SimpleNamespace:
    return SimpleNamespace(
        api_keys=frozenset(api_keys),
        mutating_rate_limit_per_minute=rate_limit,
        cors_allow_origins=tuple(cors),
    )


def _build_client(config) -> TestClient:
    guard = build_mutating_guard(config)
    app = FastAPI()

    # Mirror the production app's handler that returns dict details verbatim.
    @app.exception_handler(HTTPException)
    async def _http_exception_handler(
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

    @app.post("/mutate", dependencies=[Depends(guard)])
    def mutate() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/open")
    def open_route() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


class MutatingGuardAuthTest(unittest.TestCase):
    def test_missing_key_returns_401(self) -> None:
        client = _build_client(_config(api_keys=("secret-a",)))
        response = client.post("/mutate")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "missing_api_key")

    def test_wrong_key_returns_403(self) -> None:
        client = _build_client(_config(api_keys=("secret-a",)))
        response = client.post("/mutate", headers={"X-API-Key": "nope"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "invalid_api_key")

    def test_correct_key_returns_200(self) -> None:
        client = _build_client(_config(api_keys=("secret-a", "secret-b")))
        response = client.post("/mutate", headers={"X-API-Key": "secret-b"})
        self.assertEqual(response.status_code, 200)

    def test_open_when_no_keys_configured(self) -> None:
        client = _build_client(_config(api_keys=()))
        response = client.post("/mutate")
        self.assertEqual(response.status_code, 200)


class MutatingGuardRateLimitTest(unittest.TestCase):
    def test_exceeding_limit_returns_429_with_retry_after(self) -> None:
        client = _build_client(_config(api_keys=("k",), rate_limit=3))
        headers = {"X-API-Key": "k"}
        for _ in range(3):
            self.assertEqual(client.post("/mutate", headers=headers).status_code, 200)
        blocked = client.post("/mutate", headers=headers)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["error"], "rate_limited")
        self.assertIn("retry-after", {k.lower() for k in blocked.headers})
        self.assertGreaterEqual(int(blocked.headers["Retry-After"]), 1)

    def test_distinct_keys_do_not_share_a_bucket(self) -> None:
        client = _build_client(_config(api_keys=("k1", "k2"), rate_limit=2))
        for _ in range(2):
            self.assertEqual(
                client.post("/mutate", headers={"X-API-Key": "k1"}).status_code, 200
            )
        # k1 is now exhausted, but k2 has its own independent bucket.
        self.assertEqual(
            client.post("/mutate", headers={"X-API-Key": "k1"}).status_code, 429
        )
        self.assertEqual(
            client.post("/mutate", headers={"X-API-Key": "k2"}).status_code, 200
        )
        self.assertEqual(
            client.post("/mutate", headers={"X-API-Key": "k2"}).status_code, 200
        )

    def test_limit_zero_disables_rate_limiting(self) -> None:
        client = _build_client(_config(api_keys=(), rate_limit=0))
        for _ in range(50):
            self.assertEqual(client.post("/mutate").status_code, 200)

    def test_ip_identity_used_when_no_key(self) -> None:
        # No API keys -> auth is open, identity falls back to client host.
        client = _build_client(_config(api_keys=(), rate_limit=2))
        self.assertEqual(client.post("/mutate").status_code, 200)
        self.assertEqual(client.post("/mutate").status_code, 200)
        self.assertEqual(client.post("/mutate").status_code, 429)


if __name__ == "__main__":
    unittest.main()
