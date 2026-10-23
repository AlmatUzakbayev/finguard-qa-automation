# Test Strategy — FinGuard

## 1. What is being tested

FinGuard is a training banking service: users register, open accounts, top up, transfer money
and view their transaction history. It consists of:

- **REST API** (FastAPI + PostgreSQL) — the main object of testing;
- **Web UI** (static HTML/JS served by the same app) — a thin client over the API.

The most important quality attribute is **correctness of money movement**: money must never be
created, lost or debited twice, and one user must never access another user's money or data.

## 2. Risk-based priorities

| Risk | Impact | Likelihood | Covered by |
|---|---|---|---|
| Double debit on retry / double click | Critical | High (networks retry) | Idempotency tests (API + UI) |
| Race condition → negative balance | Critical | Medium | Parallel transfer tests, DB CHECK constraint test |
| Partial transfer (debit without credit) | Critical | Low | White-box atomicity test, ledger reconciliation |
| Access to another user's account (BOLA/IDOR) | Critical | Medium | Foreign account tests on every endpoint |
| Broken auth (missing/expired/forged token) | High | Medium | Parametrised token tests |
| Wrong amount handling (float, 3 decimals, ≤ 0) | High | Medium | Negative + boundary tests |
| Server errors on unexpected input (500) | Medium | Medium | Validation tests, BUG-001 regression |
| Contract drift (field renamed/removed) | Medium | Medium | Contract tests with strict schemas |
| UI shows wrong data / does not report errors | Medium | Low | Playwright tests |

The test effort follows this table: most tests sit where the impact is critical.

## 3. Test levels and the testing pyramid

```
            /\        UI (Playwright): ~10 critical user journeys
           /  \       - real browser, real server, real DB
          /----\
         /      \     API (pytest + httpx): ~35 test functions / ~90 cases
        /        \    - black-box over HTTP + direct DB checks
       /----------\
      /            \  Database constraints: CHECK / UNIQUE checked directly
     /--------------\
```

- **API tests are the base**: fast, stable, close to the business logic.
- **UI tests** verify only what the API tests cannot: that the page renders data, reports errors,
  and that the browser flow (login → transfer → history → logout) works end to end.
- Test data for UI tests is created **through the API**, and the UI test checks results through
  the API as well. Only the behaviour under test goes through the browser.

## 4. Test types and techniques

| Type | Technique | Example |
|---|---|---|
| Functional | Use-case / happy path | Transfer moves money between users |
| Negative | Error guessing, invalid partitions | Amount `-10`, `0`, `abc`, `NaN`, `null` |
| Boundary | Boundary value analysis (on / below / above) | `0.01`, `balance`, `balance + 0.01`, `1 000 000.00`, `1 000 000.01` |
| Equivalence partitioning | One representative per class | currencies: supported (`KZT`) vs unsupported (`RUB`, `kzt`, `""`) |
| Security (basic) | BOLA/IDOR, authentication bypass | Foreign account → `404`, same answer as non-existent |
| Database | State verification | Balances and rows in PostgreSQL after each operation |
| Concurrency | Invariant-based parallel testing | 10 × 30.00 against a balance of 100.00 → exactly 3 succeed |
| Contract | Schema validation | Strict Pydantic models, `extra="forbid"` |
| Regression | Bug-driven | BUG-001 tests |

## 5. Principles

1. **Every test is independent.** Each test creates its own users and accounts (unique emails);
   no test depends on another one or on execution order.
2. **Arrange through the API, assert through the API and the DB.** A `201` response is not
   proof; the stored balance and the transaction rows are.
3. **Check what must NOT happen.** After every rejected operation the tests assert that balances
   did not change and no transaction row appeared.
4. **No sleeps.** API concurrency uses a `threading.Barrier`; UI tests use Playwright's
   auto-waiting `expect()`.
5. **Deterministic concurrency tests.** Assertions are on invariants valid for any interleaving,
   never on which request wins.
6. **Readable failures.** Helper assertions print method, path, status and body.
7. **Tests do not import application schemas** for contract checks — the contract is written
   independently in `tests/support/contracts.py`.

## 6. Environments

| Environment | Database | How the server starts |
|---|---|---|
| Local | PostgreSQL 16 (`finguard_test` DB) | Automatically by `tests/conftest.py` (uvicorn subprocess) |
| Local, external server | Any | `API_BASE_URL=http://...` — the suite uses that server |
| CI (GitHub Actions) | `postgres:16-alpine` service container | Automatically by `tests/conftest.py` |

## 7. Entry and exit criteria

**Entry:** the application starts, migrations apply, `/health` returns 200.

**Exit (for a release of this project):**
- all API and UI tests pass, Ruff reports no issues;
- no open bugs of severity Critical/High;
- known limitations are documented in `known_issues.md`.

## 8. Out of scope

Performance/load testing, penetration testing, accessibility audit, cross-browser runs,
mobile layouts. These are listed as possible next steps in `test_plan.md`.
