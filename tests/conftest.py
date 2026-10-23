"""Shared fixtures for API and UI tests.

By default the test session:
1. checks that PostgreSQL (TEST_DATABASE_URL) is reachable,
2. applies Alembic migrations to the test database,
3. starts the application with uvicorn on a free port, in a subprocess,
4. stops it at the end.
Set API_BASE_URL to run the tests against an already running server instead
(for example one started with docker compose).

Isolation strategy: every test creates its own users and accounts with unique
emails, so tests never depend on each other or on execution order, and the
database never has to be wiped between tests.
"""

import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from tests.support.api_client import FinGuardApi
from tests.support.assertions import assert_status
from tests.support.db import DbInspector

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/finguard_test"
)
# Must match the secret of the server under test (used to forge expired tokens).
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me")
DEFAULT_PASSWORD = "Str0ng-Passw0rd!"


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}.{uuid.uuid4().hex[:12]}@example.com"


# ---------------------------------------------------------------- infrastructure


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        pytest.exit(
            f"PostgreSQL is not reachable at {TEST_DATABASE_URL}.\n"
            f"Start it (e.g. `docker compose up -d db`) or set TEST_DATABASE_URL.\n{exc}",
            returncode=3,
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def db(db_engine) -> DbInspector:
    return DbInspector(db_engine)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url(db_engine) -> Iterator[str]:
    external = os.getenv("API_BASE_URL")
    if external:
        yield external.rstrip("/")
        return

    env = {
        **os.environ,
        "DATABASE_URL": TEST_DATABASE_URL,
        "JWT_SECRET": JWT_SECRET,
        # Password hashing is slow on purpose (600k rounds); tests create hundreds of users.
        "PASSWORD_HASH_ITERATIONS": os.getenv("PASSWORD_HASH_ITERATIONS", "1000"),
    }
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)

    REPORTS.mkdir(exist_ok=True)
    port = _free_port()
    log = open(REPORTS / "server.log", "w")  # noqa: SIM115 - closed in teardown
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while True:
        if proc.poll() is not None:
            log.close()
            pytest.exit(f"Server exited with code {proc.returncode}, see reports/server.log", returncode=3)
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except httpx.TransportError:
            pass
        if time.monotonic() > deadline:
            proc.kill()
            pytest.exit("Server did not become healthy within 30s, see reports/server.log", returncode=3)
        time.sleep(0.2)  # polling a readiness probe, not synchronising a test

    yield url

    proc.terminate()
    proc.wait(timeout=10)
    log.close()


# ---------------------------------------------------------------- test data


@dataclass
class TestUser:
    __test__ = False  # not a test class, despite the name

    id: int
    email: str
    password: str
    full_name: str
    token: str
    api: FinGuardApi  # client already authorised as this user


@pytest.fixture
def anon_api(base_url) -> Iterator[FinGuardApi]:
    api = FinGuardApi(base_url)
    yield api
    api.close()


@pytest.fixture
def user_factory(base_url) -> Iterator[Callable[..., TestUser]]:
    """Register and log in a brand-new user: user_factory(full_name="Bob")."""
    clients: list[FinGuardApi] = []

    def create(full_name: str = "Test User", password: str = DEFAULT_PASSWORD) -> TestUser:
        api = FinGuardApi(base_url)
        clients.append(api)
        email = unique_email()
        registered = api.register(email, password, full_name)
        assert_status(registered, 201)
        login = api.login(email, password)
        assert_status(login, 200)
        api.token = login.json()["access_token"]
        return TestUser(registered.json()["id"], email, password, full_name, api.token, api)

    yield create
    for api in clients:
        api.close()


@pytest.fixture
def user(user_factory) -> TestUser:
    return user_factory()


@pytest.fixture
def other_user(user_factory) -> TestUser:
    return user_factory(full_name="Other User")


@pytest.fixture
def account_factory() -> Callable[..., dict]:
    """Open an account for `owner` and optionally fund it: account_factory(user, balance="100.00")."""

    def create(owner: TestUser, balance: str | Decimal = "0.00", currency: str = "KZT") -> dict:
        created = owner.api.create_account(currency)
        assert_status(created, 201)
        account = created.json()
        if Decimal(balance) > 0:
            funded = owner.api.deposit(account["id"], balance)
            assert_status(funded, 200)
            account = funded.json()
        return account

    return create
