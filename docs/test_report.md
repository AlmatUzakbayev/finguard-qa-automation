# Test Report — FinGuard v1.0

| Item | Value |
|---|---|
| Date | 2026-10-23 |
| Build | local working copy (first commit of the repository) |
| Environment | Windows 10 Pro, Python 3.14.0, PostgreSQL 16.4 (local portable install), Chromium headless (Playwright 1.64.1) |
| Key packages | FastAPI 0.161, SQLAlchemy 2.1, psycopg 3.3, pytest 9.1, httpx 0.28, pytest-playwright 0.10 |
| Not executed | GitHub Actions (repository not pushed yet), Docker Compose (Docker not installed on this machine) |

## 1. Summary

| Suite | Test functions | Test cases | Passed | Failed | Skipped |
|---|---|---|---|---|---|
| API (`tests/api`) | 43 | 90 | 90 | 0 | 0 |
| UI (`tests/ui`) | 10 | 17 | 17 | 0 | 0 |
| **Total** | **53** | **107** | **107** | **0** | **0** |

Final full runs (`pytest tests`), executed twice in a row to check stability:

| Run | Result | Duration |
|---|---|---|
| Final run 1 | 107 passed | 3 min 02 s |
| Final run 2 | 107 passed | 2 min 32 s |

Static analysis: `ruff check .` — all checks passed; `ruff format --check .` — all files formatted.

Cases by category (a case can have several markers):

| Marker | Cases |
|---|---|
| negative | 48 |
| ui | 17 |
| boundary | 14 |
| functional | 12 |
| smoke | 8 |
| db | 7 |
| contract | 6 |
| concurrency | 3 |

## 2. Run history (nothing hidden)

| # | What was run | Result | Notes |
|---|---|---|---|
| 1 | API suite, first run | **85 passed, 4 failed**, 592 s | The 4 failures were the new tests for **BUG-001** (HTTP 500 on ids outside INTEGER range) — expected, the bug was not fixed yet. Run time was too long → investigated (see §4). |
| 2 | API suite after fixing BUG-001 and speeding up hashing | 90 passed, 172 s | One more regression test added for the transfer body. |
| 3 | UI suite, first run | **Hung** after 10 tests, killed manually | No error was produced; not reproduced in any later run. Mitigation: `pytest-timeout` (`--timeout=120`) added so a hang becomes a failure with a stack trace. Root cause unknown. |
| 4 | UI suite | 17 passed, 105 s | |
| 5 | Full suite | 107 passed, 272 s (verbose mode) | |
| 6–7 | Mutation analysis (§3) | 20 mutants: 19 killed, 1 survived (explained) | One batch step returned *errors* instead of failures (environment glitch, server did not start); re-run separately and confirmed. |
| 8–9 | Final full runs | 107 passed ×2 | |

## 3. Mutation check

To verify that the tests detect real defects, realistic bugs were injected into the application **one at a
time**; the relevant tests were run; the original code was restored byte-for-byte afterwards.
"Killed" = at least one test failed, i.e. the bug would have been caught.

| # | Injected bug | Result | Failing tests (observed message) |
|---|---|---|---|
| M1 | `SELECT … FOR UPDATE` removed | Killed | `test_parallel_transfers_never_overdraw_the_account` (`got {201: 10}` — all 10 × 30.00 transfers passed on 100.00), `test_opposite_parallel_transfers…` |
| M2 | Idempotency-key lookup removed | Killed | `test_retry_with_same_idempotency_key…` (retry → 500), `test_reusing_idempotency_key…`, `test_parallel_retries…` |
| M3 | Ownership check on source account removed | Killed | `test_cannot_transfer_from_someone_elses_account` |
| M4 | `balance < amount` → `balance <= amount` | Killed | `test_transfer_amount_boundaries[amount-equals-balance]`, `[maximum-amount]` |
| M5 | Currency check removed | Killed | `test_transfer_between_different_currencies_is_rejected` |
| M6 | Ownership check on account reads removed | Killed | `test_foreign_account_is_indistinguishable_from_missing_one` (3 of 4 cases; deposit has its own check) |
| M7 | Minimum amount lowered to 0 | Killed | invalid-amount `[zero]`, `[zero-with-decimals]`, deposit `[zero]` (500 from DB CHECK) |
| M8 | Commit right after the debit (non-atomic) | Killed | `test_transfer_is_rolled_back_completely_if_it_fails_midway` |
| M9 | UI: "Send" button not disabled during request | **Survived** | Double click still produced one transfer, because the form reuses the same Idempotency-Key. Defense in depth, not a gap. See M10. |
| M10 | UI: button not disabled **and** a new key per click | Killed | `test_double_click_on_send_creates_only_one_transfer` |
| M11 | Credit to receiver removed | Killed | `test_transfer_moves_money_between_users`, `test_transfer_is_persisted_exactly`, `test_balances_reconcile_with_transaction_ledger` |
| M12 | Insufficient-funds check removed | Killed | insufficient-funds test (500), parallel test `{201: 3, 500: 7}` — DB CHECK prevented the overdraft, clients got 500 |
| M13 | Expired tokens accepted | Killed | `test_profile_rejects_missing_or_invalid_token[expired-token]` (200 instead of 401) |
| M14 | `password_hash` added to user response | Killed | `test_successful_responses_match_contract` (`Extra inputs are not permitted`), `test_register_returns_created_user_without_password` |
| M15 | Login says "User not found" for unknown email | Killed | `test_login_failure_does_not_reveal_which_part_is_wrong[unknown-email]` |
| M16 | Idempotency key not stored | Killed | `test_parallel_retries…` (`{201: 2, 422: 8}` — **double charge**), 3 more |
| M17 | BUG-001 re-introduced | Killed | `test_invalid_account_id_is_rejected_by_validation` (4 cases) |
| M18 | UI: login redirects to the wrong page | Killed | `test_login_with_valid_credentials_opens_dashboard` |
| M19 | UI: protected pages do not redirect | Killed | `test_protected_page_redirects_anonymous_user_to_login` (4 cases) |
| M20 | UI: logout keeps the token | Killed | `test_logout_ends_the_session` |

**Observation:** in M1 the parallel *retries with the same key* test still passed — the `UNIQUE` constraint
on the idempotency key rejected the duplicates at the database level. Two independent layers protect against
double charging, and the tests show which layer handles which failure.

**Known gap (found by code review, not by running a mutant):** no test checks that the `description` field is
part of the idempotency fingerprint (same key + different description should give `409`). If it were dropped
from `_request_hash`, the current tests would most likely not notice. Left as practical exercise 9.

## 4. Defects found

| ID | Summary | Severity | Status |
|---|---|---|---|
| BUG-001 | Account id outside PostgreSQL INTEGER range → HTTP 500 | Medium | Fixed, regression tests added |

Details: [known_issues.md](known_issues.md).

## 5. Test infrastructure issues found and fixed

| Issue | Finding | Fix |
|---|---|---|
| API suite took ~10 minutes | Profiling: one PBKDF2 hash (600k iterations) took **2.57 s** on this machine; every test registers and logs in users | `PASSWORD_HASH_ITERATIONS` setting; tests run the server with 1000. Production default unchanged. 592 s → 172 s |
| ~2 s delay per request | `localhost` resolved to IPv6 first on Windows; server listens on IPv4 | Use `127.0.0.1` in all URLs |
| Slow start-up (12–25 s) | `import fastapi` alone took ~6 s — environment (most likely antivirus scanning) | Not fixable in the project; documented |
| UI run hung once | Not reproduced | `pytest-timeout` |

## 6. Not verified / open items

1. ~~GitHub Actions workflow has not run yet.~~ Verified on 2026-10-28: the first run on GitHub passed
   (lint, API and UI tests on Python 3.12), which also closes the Python 3.12 question below.
2. **Docker Compose** (`docker compose up`) has not been run.
3. UI tests ran only in **Chromium**.
4. ~~Tests ran on Python 3.14; CI is configured for Python 3.12.~~ Verified by the CI run above.

## 7. Conclusion

All 107 automated tests pass reliably on the local environment. The tests are shown to detect 19 of 20
injected defects; the remaining one is covered by a second safeguard. One real defect (BUG-001) was found
and fixed. The CI pipeline and Docker setup are written but not yet executed — these are the next steps.
