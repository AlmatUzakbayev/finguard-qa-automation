"""A thin client for the FinGuard API.

Methods return the raw httpx.Response: the *test* decides which status code is
expected, the client never hides errors. Used by API tests and for UI test setup.
"""

import uuid
from decimal import Decimal

import httpx


class FinGuardApi:
    def __init__(self, base_url: str, token: str | None = None):
        self.http = httpx.Client(base_url=base_url, timeout=15)
        self.token = token

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        headers.update(extra or {})
        return headers

    def close(self) -> None:
        self.http.close()

    # --- auth ---
    def register(self, email: str, password: str, full_name: str) -> httpx.Response:
        return self.http.post("/api/auth/register", json={"email": email, "password": password, "full_name": full_name})

    def login(self, email: str, password: str) -> httpx.Response:
        return self.http.post("/api/auth/login", json={"email": email, "password": password})

    def me(self, headers: dict[str, str] | None = None) -> httpx.Response:
        return self.http.get("/api/users/me", headers=headers if headers is not None else self._headers())

    # --- accounts ---
    def create_account(self, currency: str | None = None) -> httpx.Response:
        body = {} if currency is None else {"currency": currency}
        return self.http.post("/api/accounts", json=body, headers=self._headers())

    def list_accounts(self) -> httpx.Response:
        return self.http.get("/api/accounts", headers=self._headers())

    def get_account(self, account_id: int | str) -> httpx.Response:
        return self.http.get(f"/api/accounts/{account_id}", headers=self._headers())

    def get_balance(self, account_id: int | str) -> httpx.Response:
        return self.http.get(f"/api/accounts/{account_id}/balance", headers=self._headers())

    def deposit(self, account_id: int | str, amount: str | Decimal) -> httpx.Response:
        return self.http.post(
            f"/api/accounts/{account_id}/deposit", json={"amount": str(amount)}, headers=self._headers()
        )

    def history(self, account_id: int | str, **params: int) -> httpx.Response:
        return self.http.get(f"/api/accounts/{account_id}/transactions", params=params, headers=self._headers())

    # --- transfers ---
    def transfer(
        self,
        from_id: int,
        to_id: int,
        amount: str | Decimal | None,
        key: str | None = None,
        description: str | None = None,
    ) -> httpx.Response:
        """POST /api/transfers. A fresh Idempotency-Key is generated unless one is given."""
        body: dict = {"from_account_id": from_id, "to_account_id": to_id, "amount": amount}
        if description is not None:
            body["description"] = description
        headers = self._headers({"Idempotency-Key": key or str(uuid.uuid4())})
        return self.http.post("/api/transfers", json=body, headers=headers)
