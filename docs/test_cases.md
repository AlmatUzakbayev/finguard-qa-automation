# Test Cases — FinGuard

Every automated test is listed here with the rule it protects (BR-xx, see
[test_plan.md](test_plan.md)). "Cases" = number of parametrised runs.

Totals: **API — 43 test functions / 90 cases**, **UI — 10 test functions / 17 cases**.

## API — Authentication (`tests/api/test_auth.py`)

| ID | Test | Type | Cases | Steps → Expected result | Rule |
|---|---|---|---|---|---|
| API-AUTH-01 | `test_register_returns_created_user_without_password` | Functional, smoke | 1 | Register a new email → `201`, body has id/email/full_name, **no** password fields | BR-01 |
| API-AUTH-02 | `test_register_duplicate_email_is_rejected_case_insensitively` | Negative | 1 | Register `x@...`, then `X@...` → `409 EMAIL_TAKEN` | BR-01 |
| API-AUTH-03 | `test_register_with_invalid_payload_returns_422` | Negative | 5 | Valid payload with one broken field (bad email, short password, empty/null name, unknown field) → `422`, error points at that field | BR-01, BR-10 |
| API-AUTH-04 | `test_login_returns_bearer_token_that_opens_profile` | Functional, smoke | 1 | Login → `200`, `token_type=bearer`, the token opens `/users/me` | BR-02 |
| API-AUTH-05 | `test_login_failure_does_not_reveal_which_part_is_wrong` | Negative, security | 2 | Wrong password / unknown email → `401` with the **same** message | BR-02 |
| API-AUTH-06 | `test_profile_rejects_missing_or_invalid_token` | Negative, security | 6 | No header, garbage token, `Basic` scheme, token signed with another secret, **expired** token, token of non-existent user → `401` + exact reason + `WWW-Authenticate: Bearer` | BR-02 |
| API-AUTH-07 | `test_protected_endpoints_require_authentication` | Negative | 5 | 5 protected endpoints without token → `401` | BR-02 |
| API-AUTH-08 | `test_profile_returns_current_user` | Functional | 1 | `/users/me` returns the logged-in user | BR-02 |

## API — Accounts (`tests/api/test_accounts.py`)

| ID | Test | Type | Cases | Steps → Expected result | Rule |
|---|---|---|---|---|---|
| API-ACC-01 | `test_create_account_starts_with_zero_balance` | Functional, smoke | 3 | Open account with default/USD/EUR → `201`, right currency, balance `"0.00"` | — |
| API-ACC-02 | `test_create_account_with_unsupported_currency_returns_422` | Negative | 4 | `RUB`, `kzt`, `""`, `KZTT` → `422` | — |
| API-ACC-03 | `test_deposit_increases_balance` | Functional | 1 | 150.25 + 49.75 → balance `"200.00"` | BR-04 |
| API-ACC-04 | `test_account_list_contains_only_own_accounts` | Negative, security | 1 | List shows exactly own accounts, never foreign ones | BR-03 |
| API-ACC-05 | `test_foreign_account_is_indistinguishable_from_missing_one` | Negative, security | 4 | GET account / balance / history / deposit on a foreign account → `404`, response identical to a non-existent id; victim's balance unchanged | BR-03 |
| API-ACC-06 | `test_invalid_account_id_is_rejected_by_validation` | Negative, regression | 5 | Ids `0`, `-1`, `2147483648`, `99999999999999999999`, `abc` → `422` (was `500`, **BUG-001**) | BR-10 |

## API — Transfers (`tests/api/test_transfers.py`)

| ID | Test | Type | Cases | Steps → Expected result | Rule |
|---|---|---|---|---|---|
| API-TRF-01 | `test_transfer_moves_money_between_users` | Functional, smoke | 1 | 1000.00 → transfer 250.50 → `201`; sender `749.50`, receiver `250.50` | BR-05 |
| API-TRF-02 | `test_history_shows_debit_for_sender_and_credit_for_receiver` | Functional | 1 | Sender sees DEBIT + DEPOSIT (newest first); receiver sees one CREDIT with counterparty and description | BR-09 |
| API-TRF-03 | `test_history_pagination` | Functional | 1 | 3 deposits, `limit=2&offset=1` → the 2nd and 3rd newest | — |
| API-TRF-04 | `test_transfer_with_invalid_amount_is_rejected_and_changes_nothing` | Negative | 7 | Amount `-10.00`, `0`, `0.00`, `0.001`, `abc`, `NaN`, `null` → `422` on `amount`; balance and DB unchanged | BR-04 |
| API-TRF-05 | `test_transfer_with_insufficient_funds_is_rejected_and_changes_nothing` | Negative | 1 | 50.00 balance, transfer 50.01 → `422 INSUFFICIENT_FUNDS`; both balances unchanged | BR-05 |
| API-TRF-06 | `test_cannot_transfer_from_someone_elses_account` | Negative, security | 1 | Attacker uses victim's account as source → `404`; no money moved | BR-03 |
| API-TRF-07 | `test_transfer_to_nonexistent_account_returns_404` | Negative | 1 | Destination does not exist → `404 Destination account not found`; balance unchanged | — |
| API-TRF-08 | `test_transfer_to_out_of_range_account_id_is_rejected` | Negative, regression | 1 | `to_account_id = 99999999999` → `422` (was `500`, **BUG-001**) | BR-10 |
| API-TRF-09 | `test_transfer_to_the_same_account_is_rejected` | Negative | 1 | from = to → `422` | BR-06 |
| API-TRF-10 | `test_transfer_between_different_currencies_is_rejected` | Negative | 1 | KZT → USD → `422 CURRENCY_MISMATCH` | BR-06 |
| API-TRF-11 | `test_transfer_without_idempotency_key_is_rejected` | Negative | 1 | No `Idempotency-Key` header → `422`, error on that header | BR-07 |

## API — Boundaries (`tests/api/test_boundaries.py`)

| ID | Test | Type | Cases | Steps → Expected result | Rule |
|---|---|---|---|---|---|
| API-BND-01 | `test_transfer_amount_boundaries` | Boundary | 5 | `0.01` ✅, amount = balance ✅ (→ `0.00`), balance + 0.01 ❌, `1 000 000.00` ✅, `1 000 000.01` ❌ | BR-04, BR-05 |
| API-BND-02 | `test_over_limit_transfer_fails_validation_even_with_enough_money` | Boundary | 1 | Balance 2 000 000, transfer 1 000 000.01 → `422 less_than_equal` (limit, not balance) | BR-04 |
| API-BND-03 | `test_deposit_amount_boundaries` | Boundary | 4 | `0.00` ❌, `0.01` ✅, `1 000 000.00` ✅, `1 000 000.01` ❌ | BR-04 |
| API-BND-04 | `test_password_length_boundaries` | Boundary | 4 | 7 ❌, 8 ✅, 128 ✅, 129 ❌ | BR-01 |

## API — Database (`tests/api/test_database.py`)

| ID | Test | Type | Cases | Steps → Expected result | Rule |
|---|---|---|---|---|---|
| API-DB-01 | `test_transfer_is_persisted_exactly` | DB | 1 | After transfer 123.45: exact balances in `accounts`, exactly one `transactions` row with amount, initiator, idempotency key | BR-08 |
| API-DB-02 | `test_rejected_transfer_leaves_no_trace_in_database` | DB | 1 | After `INSUFFICIENT_FUNDS`: balances unchanged, no new rows | BR-05, BR-08 |
| API-DB-03 | `test_transfer_is_rolled_back_completely_if_it_fails_midway` | DB, white-box | 1 | Crash injected after the debit (verified 70.00 inside the DB transaction) → after the failure balance is 100.00, no rows | BR-08 |
| API-DB-04 | `test_database_constraints_protect_invariants` | DB | 3 | Direct SQL: negative balance, zero amount, self-transfer → rejected by CHECK constraints | BR-04, BR-05, BR-06 |
| API-DB-05 | `test_balances_reconcile_with_transaction_ledger` | DB | 1 | Mixed successful and failed transfers among 3 accounts → each balance = ledger; total money unchanged | BR-09 |

## API — Idempotency & concurrency (`tests/api/test_idempotency_and_concurrency.py`)

| ID | Test | Type | Cases | Steps → Expected result | Rule |
|---|---|---|---|---|---|
| API-IDM-01 | `test_retry_with_same_idempotency_key_returns_original_transfer` | Functional | 1 | Same key twice → `201`, then `200` with identical body and `Idempotent-Replayed: true`; debited once | BR-07 |
| API-IDM-02 | `test_reusing_idempotency_key_with_different_body_is_a_conflict` | Negative | 1 | Same key, different amount → `409 IDEMPOTENCY_KEY_REUSED`; no second debit | BR-07 |
| API-IDM-03 | `test_idempotency_keys_are_scoped_per_user` | Functional | 1 | Two users, same key → both `201` | BR-07 |
| API-CON-01 | `test_parallel_retries_with_same_key_debit_only_once` | Concurrency | 1 | 10 parallel identical requests → exactly one `201` + nine `200`, one transfer id, one row, debited once | BR-07 |
| API-CON-02 | `test_parallel_transfers_never_overdraw_the_account` | Concurrency | 1 | 10 × 30.00 in parallel against 100.00 → exactly 3 × `201`, 7 × `422`; final 10.00 / 90.00 | BR-05 |
| API-CON-03 | `test_opposite_parallel_transfers_do_not_deadlock_or_lose_money` | Concurrency | 1 | 10 × A→B and 10 × B→A in parallel → all 20 `201`, balances unchanged | BR-05, BR-08 |

## API — Contract (`tests/api/test_contract.py`)

| ID | Test | Type | Cases | Steps → Expected result | Rule |
|---|---|---|---|---|---|
| API-CTR-01 | `test_successful_responses_match_contract` | Contract | 1 | Every success response of the main flow matches a strict schema (no extra fields); money is a string with 2 decimals | BR-10 |
| API-CTR-02 | `test_error_responses_share_one_format` | Contract | 4 | 401 / 404 / 409 / 422 → `application/json`, `{code, detail}` | BR-10 |
| API-CTR-03 | `test_openapi_schema_is_published` | Contract | 1 | `/openapi.json` contains the key endpoints | — |

## UI — Playwright (`tests/ui/`)

| ID | Test | Cases | Steps → Expected result |
|---|---|---|---|
| UI-01 | `test_login_with_valid_credentials_opens_dashboard` (smoke) | 1 | Login form → dashboard URL, "Welcome, <name>", name in header |
| UI-02 | `test_login_with_wrong_password_shows_error` | 1 | Error "Invalid email or password.", still on login page |
| UI-03 | `test_protected_page_redirects_anonymous_user_to_login` | 4 | Dashboard / Accounts / Transfer / History without session → login page |
| UI-04 | `test_logout_ends_the_session` | 1 | Sign out → message shown; opening dashboard again → login page |
| UI-05 | `test_dashboard_shows_balance_of_each_account` | 1 | Accounts created via API → dashboard shows `15000.50 KZT`, `20.00 USD` |
| UI-06 | `test_open_account_and_top_up` | 1 | Open EUR account and top up 99.90 in the UI → table and API show `99.90` |
| UI-07 | `test_transfer_updates_balance_and_shows_confirmation` (smoke) | 1 | Transfer 120.75 → confirmation; balances checked via API |
| UI-08 | `test_transfer_form_shows_validation_errors` | 5 | Missing recipient, missing amount, `0`, `10.999`, more than balance → exact error text, no success message, balance unchanged |
| UI-09 | `test_double_click_on_send_creates_only_one_transfer` | 1 | Double click "Send money" → exactly one debit in history |
| UI-10 | `test_history_shows_transfer_for_sender_and_receiver` | 1 | Sender sees `-45.00` with description and counterparty; receiver sees `+45.00` |

## Manual / exploratory checks performed

| Check | Result |
|---|---|
| Account id boundaries in URL (`2147483647`, `2147483648`, huge, `0`, `-1`) | Found **BUG-001** (500), fixed |
| `curl` walk-through of the whole API | OK |
| Replay response header `Idempotent-Replayed` | OK (covered by API-IDM-01) |
