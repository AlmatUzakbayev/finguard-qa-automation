# Known Issues and Bug Reports

This file has two parts: **bugs found during testing** (with their status) and **known
limitations** of the training application and of the test suite. Nothing here is hidden:
if a check fails or something was not verified, it is listed.

## Part 1. Bugs found during testing

### BUG-001 — Account id outside the INTEGER range causes HTTP 500

| Field | Value |
|---|---|
| Status | **Fixed**, covered by regression tests |
| Severity | Medium (server error; no data corruption) |
| Priority | High (trivially reproducible by any client, pollutes error monitoring) |
| Found by | Exploratory API testing (boundary values for path parameters) |
| Component | `GET/POST /api/accounts/{account_id}/...`, `POST /api/transfers` |

**Steps to reproduce (before the fix)**
1. Log in and get a token.
2. `GET /api/accounts/2147483648` with `Authorization: Bearer <token>`.

**Expected:** a client error: `422 VALIDATION_ERROR` (the id cannot exist) or `404 NOT_FOUND`.
**Actual:** `500 Internal Server Error`, plain-text body `Internal Server Error`.

The same happened for `to_account_id: 99999999999` in the body of `POST /api/transfers`.

Observed results for different ids before the fix:

| account_id | Status |
|---|---|
| 2147483647 (INT max) | 404 |
| 2147483648 (INT max + 1) | **500** |
| 99999999999999999999 | **500** |
| 0, -1 | 404 |

**Root cause:** primary keys are PostgreSQL `INTEGER` (max 2 147 483 647). FastAPI accepted any
Python `int`, and the database driver failed when converting the larger value for the query.
The exception was not handled, so the server returned 500.

**Fix:** ids are validated before they reach the database: `Path(gt=0, le=2147483647)` for
path parameters and `Field(gt=0, le=2147483647)` in `TransferRequest` (see `app/schemas.py`,
`MAX_DB_ID`). Ids `0` and negative ids are now rejected with 422 as well, instead of 404.

**Regression tests**
- `tests/api/test_accounts.py::test_invalid_account_id_is_rejected_by_validation` (5 cases)
- `tests/api/test_transfers.py::test_transfer_to_out_of_range_account_id_is_rejected`

These tests were written first and failed against the unfixed code
(`4 failed` in the first run: `zero`, `negative`, `int32-max-plus-1`, `huge`); after the fix they pass.

**Lesson:** test boundaries of *every* input, including ids in the URL, not only the "business"
fields like amount. A 500 error is always a bug, even when the input is nonsense.

## Part 2. Known limitations

### Application (by design: this is a training project)

1. **Not a real banking system.** No KYC, no audit trail, no fraud checks, no rate limiting,
   no real money. Never use it with real personal or financial data.
2. **Deposit endpoint is a training shortcut.** `POST /api/accounts/{id}/deposit` lets a user
   add money to their own account so that tests can create a balance. A real bank never has it.
3. **No currency conversion.** Transfers between accounts of different currencies are rejected
   (`422 CURRENCY_MISMATCH`).
4. **JWT has no revocation.** Logging out in the UI deletes the token from the browser, but the
   token itself stays valid until it expires (30 minutes by default). A server-side denylist or
   short-lived tokens with refresh tokens would be needed in a real system.
5. **Token is stored in `sessionStorage`.** Simple and visible for learning; an XSS bug would
   expose it. Production apps often prefer `HttpOnly` cookies.
6. **Failed transfers are not stored for idempotency.** If a transfer with key `K` fails (e.g.
   insufficient funds), a retry with the same `K` is executed again. Successful transfers are
   always replayed. This is a deliberate, documented choice.
7. **Default JWT secret is for development only.** `JWT_SECRET` must be set in any shared
   environment. The default value is intentionally named `dev-only-insecure-secret-change-me`.

### Test suite

1. **UI tests run in Chromium only.** Firefox/WebKit are supported by Playwright
   (`--browser firefox`) but were not run.
2. **Tests use a lower password hashing cost.** The test server runs with
   `PASSWORD_HASH_ITERATIONS=1000` instead of 600 000, because each hash took ~2.5 s on the
   development machine and every test registers new users. Hash *correctness* is still tested
   (registration + login), only the cost differs.
3. **The white-box atomicity test imports application code.** `test_transfer_is_rolled_back_completely_if_it_fails_midway`
   cannot run against a remote server (`API_BASE_URL`); it needs direct DB access.
4. **Concurrency tests prove the absence of races with high probability, not with certainty.**
   They assert invariants that hold for every interleaving, so they never flake on a correct
   server, but a race window could theoretically be missed in a single run.
5. **Docker Compose was not run on the development machine** (Docker is not installed there).
   The tests were run against a local PostgreSQL 16 instead. See `docs/test_report.md`.
6. **Slow test start-up on the development machine.** Importing Python packages took 12–25 s on
   Windows (most likely antivirus scanning). This affects only start-up time, not results.
