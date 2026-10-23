# Test Plan — FinGuard v1.0

| Item | Value |
|---|---|
| Product | FinGuard training banking API + web UI |
| Version | 1.0.0 |
| Author | Candidate (self-study project, built with AI assistance) |
| Related | [test_strategy.md](test_strategy.md), [test_cases.md](test_cases.md), [test_report.md](test_report.md) |

## 1. Scope

### In scope

| Feature | API | UI |
|---|---|---|
| Registration | ✅ | — (page exists, not automated) |
| Login / token validation | ✅ | ✅ |
| Profile (`/users/me`) | ✅ | ✅ (name in header) |
| Open account (KZT / USD / EUR) | ✅ | ✅ |
| Top up (training deposit) | ✅ | ✅ |
| Balance | ✅ | ✅ |
| Transfers between accounts | ✅ | ✅ |
| Idempotency of transfers | ✅ | ✅ (double click) |
| Transaction history + pagination | ✅ | ✅ |
| Access control between users | ✅ | ✅ (protected pages) |
| Error format and HTTP status codes | ✅ | ✅ (error messages) |
| Logout | — (stateless JWT) | ✅ |

### Out of scope
Performance, load, penetration testing, accessibility, cross-browser, mobile, localisation.

## 2. Business rules under test

| ID | Rule |
|---|---|
| BR-01 | Email is unique, case-insensitive. Password length 8–128. |
| BR-02 | Every endpoint except register/login/health requires a valid, unexpired Bearer token. |
| BR-03 | A user sees and operates only their own accounts. Foreign accounts answer `404`, like missing ones. |
| BR-04 | Amounts: minimum `0.01`, at most 2 decimal places, maximum `1 000 000.00` per transfer / deposit. |
| BR-05 | A transfer cannot exceed the balance; the balance can never become negative. |
| BR-06 | Transfers only between different accounts with the same currency. |
| BR-07 | Every transfer requires an `Idempotency-Key`. Same key + same body → original result (200). Same key + different body → `409`. Keys are scoped per user. |
| BR-08 | A transfer is atomic: debit, credit and the transaction record are saved together or not at all. |
| BR-09 | Balance = sum of credits − sum of debits in the transaction log (ledger invariant). |
| BR-10 | Errors have one JSON format: `{"code", "detail"}` (+ `errors` for validation). |

## 3. Approach
See [test_strategy.md](test_strategy.md). Summary: risk-based; API-first; DB state checks;
invariant-based concurrency tests; Page Object Model for UI.

## 4. Tools

| Purpose | Tool |
|---|---|
| Test runner | pytest (+ fixtures, parametrize, markers, pytest-timeout) |
| HTTP client | httpx |
| UI automation | Playwright for Python (pytest-playwright), Chromium |
| DB access | SQLAlchemy Core (raw SQL) |
| Contract | Pydantic v2 strict models |
| Reports | pytest-html (HTML), JUnit XML, Playwright traces & screenshots on failure |
| Static analysis | Ruff (lint + format) |
| CI | GitHub Actions with a PostgreSQL service container |

## 5. Test data
- Generated per test: unique emails `user.<random>@example.com`, fixed strong password.
- Balances created through the training deposit endpoint.
- No real personal or banking data is ever used.

## 6. Schedule (as executed)

| Stage | Result |
|---|---|
| 1. API + API tests | Done. One bug found and fixed (BUG-001). |
| 2. Web UI + UI tests | Done. |
| 3. CI/CD + documentation | Workflow written; **not executed yet** (requires pushing to GitHub). |
| 4. Technical audit | Done, see [test_report.md](test_report.md). |
| 5. Learning materials | Done, see `/learning`. |

## 7. Risks of the testing process

| Risk | Mitigation |
|---|---|
| Flaky concurrency tests | Invariant-based assertions, barrier start, no sleeps |
| Flaky UI tests | `data-testid` locators, auto-waiting `expect`, data created via API |
| Tests passing for the wrong reason | Each new test was checked to fail when the rule is broken (see learning materials, "how to break this test") |
| CI not verified | Explicitly stated in the report; first push to GitHub must be checked manually |

## 8. Possible next steps
- Load test of `/api/transfers` (Locust or k6) to measure throughput under lock contention.
- Cross-browser UI run (`--browser firefox --browser webkit`).
- Allure report with history and test steps.
- Schemathesis (property-based API testing from the OpenAPI schema).
