"""Application settings, read from environment variables (or a local .env file)."""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/finguard"

    # A development-only default. Any real deployment must override JWT_SECRET.
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # OWASP recommendation for PBKDF2-HMAC-SHA256. The automated tests lower it,
    # because hashing is deliberately slow and every test registers new users.
    password_hash_iterations: int = 600_000

    # Business limits. Kept in one place so tests and docs can refer to them.
    min_amount: Decimal = Decimal("0.01")
    max_transfer_amount: Decimal = Decimal("1000000.00")
    max_deposit_amount: Decimal = Decimal("1000000.00")


@lru_cache
def get_settings() -> Settings:
    return Settings()
