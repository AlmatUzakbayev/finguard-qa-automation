"""Direct read access to the test database, for checks the API cannot show
(exact stored values, rows that must NOT exist, the ledger as a whole)."""

from decimal import Decimal

from sqlalchemy import Engine, text


class DbInspector:
    def __init__(self, engine: Engine):
        self.engine = engine

    def balance(self, account_id: int) -> Decimal:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT balance FROM accounts WHERE id = :id"), {"id": account_id}).scalar_one()

    def transfers_between(self, from_id: int, to_id: int) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM transactions WHERE type = 'TRANSFER' "
                    "AND from_account_id = :f AND to_account_id = :t ORDER BY id"
                ),
                {"f": from_id, "t": to_id},
            )
            return [dict(r._mapping) for r in rows]

    def count_transactions(self, account_id: int) -> int:
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT count(*) FROM transactions WHERE from_account_id = :id OR to_account_id = :id"),
                {"id": account_id},
            ).scalar_one()

    def ledger_balance(self, account_id: int) -> Decimal:
        """Balance recomputed from the transaction log: all credits minus all debits."""
        with self.engine.connect() as conn:
            return conn.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN to_account_id = :id THEN amount ELSE -amount END), 0) "
                    "FROM transactions WHERE from_account_id = :id OR to_account_id = :id"
                ),
                {"id": account_id},
            ).scalar_one()
