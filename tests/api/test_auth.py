"""Registration, login, profile and token handling."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from tests.conftest import DEFAULT_PASSWORD, JWT_SECRET, unique_email
from tests.support.assertions import assert_error, assert_status


@pytest.mark.smoke
@pytest.mark.functional
def test_register_returns_created_user_without_password(anon_api):
    email = unique_email()

    response = anon_api.register(email, DEFAULT_PASSWORD, "Aigerim Test")

    assert_status(response, 201)
    body = response.json()
    assert body["email"] == email
    assert body["full_name"] == "Aigerim Test"
    assert isinstance(body["id"], int)
    assert not {"password", "password_hash"} & body.keys(), "Password data must never be returned"


@pytest.mark.negative
def test_register_duplicate_email_is_rejected_case_insensitively(anon_api):
    email = unique_email()
    assert_status(anon_api.register(email, DEFAULT_PASSWORD, "First"), 201)

    response = anon_api.register(email.upper(), DEFAULT_PASSWORD, "Second")

    assert_error(response, 409, "EMAIL_TAKEN")


VALID_REGISTRATION = {"email": "valid@example.com", "password": DEFAULT_PASSWORD, "full_name": "Valid Name"}


@pytest.mark.negative
@pytest.mark.parametrize(
    ("changes", "bad_field"),
    [
        pytest.param({"email": "not-an-email"}, "email", id="bad-email"),
        pytest.param({"password": "short"}, "password", id="short-password"),
        pytest.param({"full_name": ""}, "full_name", id="empty-name"),
        pytest.param({"full_name": None}, "full_name", id="null-name"),
        pytest.param({"is_admin": True}, "is_admin", id="unknown-field"),
    ],
)
def test_register_with_invalid_payload_returns_422(anon_api, changes, bad_field):
    """Start from a valid payload and break exactly one field, so a failure points to one cause."""
    payload = {**VALID_REGISTRATION, **changes}

    response = anon_api.http.post("/api/auth/register", json=payload)

    body = assert_error(response, 422, "VALIDATION_ERROR")
    error_fields = [err["loc"][-1] for err in body["errors"]]
    assert bad_field in error_fields, f"Expected an error about {bad_field!r}, got {body['errors']}"


@pytest.mark.smoke
@pytest.mark.functional
def test_login_returns_bearer_token_that_opens_profile(anon_api, user):
    response = anon_api.login(user.email, user.password)

    assert_status(response, 200)
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    profile = anon_api.me(headers={"Authorization": f"Bearer {body['access_token']}"})
    assert_status(profile, 200)
    assert profile.json()["id"] == user.id


@pytest.mark.negative
@pytest.mark.parametrize("case", ["wrong-password", "unknown-email"])
def test_login_failure_does_not_reveal_which_part_is_wrong(anon_api, user, case):
    email = user.email if case == "wrong-password" else unique_email()
    password = "Wrong-Passw0rd!" if case == "wrong-password" else user.password

    response = anon_api.login(email, password)

    body = assert_error(response, 401, "UNAUTHORIZED")
    # The same message in both cases: an attacker must not learn which emails are registered.
    assert body["detail"] == "Invalid email or password"


# A different, but properly long, HMAC key: tokens signed with it must be rejected.
ATTACKER_SECRET = "attacker-controlled-secret-0123456789abcdef"


def _token(secret: str, expires_delta: timedelta, sub: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + expires_delta}, secret, algorithm="HS256")


@pytest.mark.negative
@pytest.mark.parametrize(
    ("make_header", "expected_detail"),
    [
        pytest.param(lambda u: None, "Missing Authorization header", id="no-header"),
        pytest.param(lambda u: "Bearer not.a.jwt", "Invalid token", id="garbage-token"),
        pytest.param(lambda u: f"Basic {u.token}", "Authorization header must be 'Bearer <token>'", id="wrong-scheme"),
        pytest.param(
            lambda u: f"Bearer {_token(ATTACKER_SECRET, timedelta(minutes=5), str(u.id))}",
            "Invalid token",
            id="foreign-signature",
        ),
        pytest.param(
            lambda u: f"Bearer {_token(JWT_SECRET, timedelta(minutes=-1), str(u.id))}",
            "Token has expired",
            id="expired-token",
        ),
        pytest.param(
            lambda u: f"Bearer {_token(JWT_SECRET, timedelta(minutes=5), '999999999')}",
            "Invalid token",
            id="deleted-user",
        ),
    ],
)
def test_profile_rejects_missing_or_invalid_token(anon_api, user, make_header, expected_detail):
    header = make_header(user)
    headers = {} if header is None else {"Authorization": header}

    response = anon_api.me(headers=headers)

    body = assert_error(response, 401, "UNAUTHORIZED")
    assert body["detail"] == expected_detail
    assert response.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.negative
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/accounts"),
        ("POST", "/api/accounts"),
        ("GET", "/api/accounts/1/balance"),
        ("GET", "/api/accounts/1/transactions"),
        ("POST", "/api/transfers"),
    ],
)
def test_protected_endpoints_require_authentication(anon_api, method, path):
    response = anon_api.http.request(method, path, json={}, headers={"Idempotency-Key": "k"})

    assert_error(response, 401, "UNAUTHORIZED")


@pytest.mark.functional
def test_profile_returns_current_user(user):
    response = user.api.me()

    assert_status(response, 200)
    body = response.json()
    assert (body["id"], body["email"], body["full_name"]) == (user.id, user.email, user.full_name)
