import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from assessment_agent import auth, config
from run import app

client = TestClient(app)

CLIENT_ID = "11111111-2222-3333-4444-555555555555"
TENANT = "1b0d02db-fc9e-4495-9537-1d379cca2ae7"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(key=KEY, **overrides) -> str:
    now = int(time.time())
    claims = {
        "aud": CLIENT_ID,
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "tid": TENANT,
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "preferred_username": "prof.smith@calpoly.edu",
        "name": "Prof Smith",
        "oid": "user-oid-1",
        **overrides,
    }
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256", headers={"kid": "k1"})


def bearer(value: str) -> dict:
    return {"Authorization": f"Bearer {value}"}


@pytest.fixture
def signin_on(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MS_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(config, "AUTH_MS_TENANT_ID", TENANT)
    monkeypatch.setattr(config, "AUTH_ALLOWED_EMAIL_DOMAIN", "calpoly.edu")
    # Stands in for Microsoft's published key set.
    monkeypatch.setattr(auth, "_signing_key", lambda _token, _tenant: KEY.public_key())


def test_everything_is_open_while_signin_is_not_configured():
    assert config.AUTH_MS_CLIENT_ID == ""
    assert client.get("/assignments").status_code == 200
    assert client.get("/results").status_code == 200


def test_health_stays_open(signin_on):
    assert client.get("/health").status_code == 200


def test_requests_without_a_token_are_refused(signin_on):
    for path in ("/assignments", "/results", "/models", "/assignments/hw1_sorting/agent-config"):
        resp = client.get(path)
        assert resp.status_code == 401, path
        assert resp.headers["www-authenticate"] == "Bearer"
    assert client.get("/results", headers={"Authorization": "Basic abc"}).status_code == 401


def test_a_valid_cal_poly_token_gets_in(signin_on):
    assert client.get("/assignments", headers=bearer(token())).status_code == 200
    assert auth.verify_id_token(token()) == auth.Instructor("prof.smith@calpoly.edu", "Prof Smith", "user-oid-1")


@pytest.mark.parametrize("bad, reason", [
    (lambda: token(key=OTHER_KEY), "Signature"),
    (lambda: token(aud="someone-elses-app"), "Audience"),
    (lambda: token(iss="https://login.microsoftonline.com/other-tenant/v2.0"), "issuer"),
    (lambda: token(exp=int(time.time()) - 3600), "expired"),
    (lambda: token(tid="other-tenant"), "directory"),
    (lambda: token(preferred_username="someone@gmail.com"), "@calpoly.edu"),
    (lambda: token(preferred_username="x@calpoly.edu.evil.com"), "@calpoly.edu"),
    (lambda: token(preferred_username="calpoly.edu"), "@calpoly.edu"),
    (lambda: "not-a-jwt", "Invalid sign-in token"),
])
def test_bad_tokens_are_refused_with_a_reason(signin_on, bad, reason):
    resp = client.get("/results", headers=bearer(bad()))
    assert resp.status_code == 401
    assert reason in resp.json()["detail"]


def test_the_email_claim_is_used_when_there_is_no_preferred_username(signin_on):
    good = token(preferred_username=None, email="Prof.Smith@CalPoly.edu")
    assert auth.verify_id_token(good).email == "prof.smith@calpoly.edu"
