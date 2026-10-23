# 04. SQL, транзакции, блокировки и тестирование базы данных

## 1. Схема БД

```
users                     accounts                          transactions
-----                     --------                          ------------
id PK                     id PK                             id PK
email UNIQUE              owner_id FK -> users.id           type  'DEPOSIT' | 'TRANSFER'
full_name                 currency                          from_account_id FK (NULL для DEPOSIT)
password_hash             balance NUMERIC(18,2)             to_account_id FK
created_at                  CHECK (balance >= 0)            amount NUMERIC(18,2) CHECK (amount > 0)
                          created_at                        description
                                                            initiator_id FK -> users.id
                                                            idempotency_key, request_hash
                                                            UNIQUE (initiator_id, idempotency_key)
                                                            CHECK (from_account_id <> to_account_id)
```

Подключиться и посмотреть самому:
```bash
psql -h 127.0.0.1 -U postgres -d finguard_test        # пароль: postgres
\dt                       -- список таблиц
\d accounts               -- структура таблицы и ограничения
SELECT * FROM transactions ORDER BY id DESC LIMIT 10;
```

## 2. Полезные SQL-запросы для тестировщика

```sql
-- Баланс счёта
SELECT balance FROM accounts WHERE id = 42;

-- Все движения по счёту, новые сверху
SELECT id, type, from_account_id, to_account_id, amount, created_at
FROM transactions WHERE from_account_id = 42 OR to_account_id = 42 ORDER BY id DESC;

-- Сверка баланса с журналом операций (ledger) — должно совпадать
SELECT a.id, a.balance,
       COALESCE(SUM(CASE WHEN t.to_account_id = a.id THEN t.amount ELSE -t.amount END), 0) AS ledger
FROM accounts a
LEFT JOIN transactions t ON t.from_account_id = a.id OR t.to_account_id = a.id
GROUP BY a.id, a.balance
HAVING a.balance <> COALESCE(SUM(CASE WHEN t.to_account_id = a.id THEN t.amount ELSE -t.amount END), 0);
-- Пустой результат = все балансы сходятся с журналом

-- Дубликаты по ключу идемпотентности (должно быть пусто — UNIQUE не даст)
SELECT initiator_id, idempotency_key, count(*) FROM transactions
WHERE idempotency_key IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1;
```
Последние два запроса — **инвариантные проверки**: их можно запускать на любой БД в любой момент.

## 3. Транзакции и ACID

**Транзакция** — группа операций «всё или ничего». Перевод = 3 действия:
1. `UPDATE accounts SET balance = balance - 30 WHERE id = A`
2. `UPDATE accounts SET balance = balance + 30 WHERE id = B`
3. `INSERT INTO transactions ...`

Если сервер упадёт между шагами 1 и 2 без транзакции — деньги исчезнут. С транзакцией
(`COMMIT` только в конце) — откатится всё.

ACID: **A**tomicity (всё или ничего), **C**onsistency (ограничения соблюдены),
**I**solation (параллельные транзакции не мешают друг другу), **D**urability (после COMMIT данные не пропадут).

## 4. Гонка (race condition) и `SELECT ... FOR UPDATE`

Без блокировки два параллельных перевода по 30 со счёта со 100 и с балансом 40 после первого:
```
Запрос 1: читает баланс 40           Запрос 2: читает баланс 40
Запрос 1: 40 >= 30 → OK              Запрос 2: 40 >= 30 → OK
Запрос 1: пишет 10                   Запрос 2: пишет 10    <- lost update: списали 60, а баланс 10
```
С `FOR UPDATE` первый запрос **блокирует строку**; второй ждёт, пока первый сделает COMMIT,
и затем читает уже новое значение (10) → «недостаточно средств».

### Почему блокировки берутся в порядке возрастания id (защита от дедлока)
```
Перевод A→B блокирует A, ждёт B
Перевод B→A блокирует B, ждёт A      -> оба ждут друг друга вечно = DEADLOCK
```
В проекте `ORDER BY id` + `FOR UPDATE`: оба перевода сначала блокируют меньший id, поэтому
второй просто ждёт первого. Это проверяет `test_opposite_parallel_transfers_do_not_deadlock_or_lose_money`.

## 5. Идемпотентность

Клиент шлёт `Idempotency-Key` (UUID). Сервер:
1. блокирует счета;
2. ищет транзакцию с этим ключом у этого пользователя;
3. нашёл и тело запроса то же (сравнивается `request_hash`) → возвращает **старый** результат, `200`;
4. нашёл, но тело другое → `409`;
5. не нашёл → выполняет перевод и сохраняет ключ.

Поиск ключа идёт **после** блокировки: параллельный повтор ждёт оригинал, а потом видит его результат.
Плюс `UNIQUE (initiator_id, idempotency_key)` в БД — защита даже при ошибке в коде.

## 6. Разбор DB-тестов (tests/api/test_database.py)

### `test_transfer_is_persisted_exactly`
- **Проверяет:** точные балансы и **ровно одну** строку `transactions` с правильными полями.
- **Почему мало проверить API:** API мог вернуть 201 и ошибиться в записи (например, записать
  сумму без копеек или не сохранить ключ идемпотентности).
- **Как сломать:** в `_record_transfer` поставь `idempotency_key=None` → упадёт последний assert.

### `test_rejected_transfer_leaves_no_trace_in_database`
- После `INSUFFICIENT_FUNDS` нет новых строк и балансы те же. Проверяем **отсутствие** побочных эффектов.

### `test_transfer_is_rolled_back_completely_if_it_fails_midway` (белый ящик)
- **Идея:** через `monkeypatch` подменяем `_record_transfer` функцией, которая (1) читает баланс
  **внутри** незакоммиченной транзакции и (2) бросает исключение.
- **Assert 1:** внутри транзакции баланс уже 70.00 — значит, сбой действительно произошёл **после**
  списания (иначе тест ничего бы не доказывал).
- **Assert 2:** после сбоя в БД снова 100.00 и нет строк — списание откатилось.
- **Как сломать (проверено, мутация M8):** в `execute_transfer` замени `db.flush()` после изменения
  балансов на `db.commit()` → списание сохранится отдельно, тест покажет 70.00 вместо 100.00.

### `test_database_constraints_protect_invariants` (3 кейса)
- Прямым SQL пытаемся записать: отрицательный баланс, нулевую сумму, перевод самому себе.
- **Ожидание:** `IntegrityError` с именем нужного ограничения (`match=...`).
- **Зачем:** код можно обойти (другой сервис, ручной SQL, баг), а ограничение в БД — нет.
- **Как сломать:** напиши новую миграцию, удаляющую `ck_accounts_balance_non_negative` →
  кейс `negative-balance` упадёт с `DID NOT RAISE`.

### `test_balances_reconcile_with_transaction_ledger`
- Серия переводов, включая 2 неудачных, между 3 счетами.
- **Assert:** для каждого счёта `balance == ledger_balance` (сумма движений из журнала),
  общая сумма денег не изменилась, итоговые балансы точные.
- **Это аналог бухгалтерской сверки.** Ловит любой баг, при котором баланс и журнал расходятся.

## 7. Конкурентные тесты (test_idempotency_and_concurrency.py)

### Как сделать их воспроизводимыми
1. **Barrier** — все потоки стартуют одновременно → максимальное перекрытие запросов.
2. **Assert на инварианты, а не на порядок.** Мы не знаем, какие 3 перевода из 10 пройдут, но знаем,
   что **ровно 3** (100 / 30 = 3, остаток 10). Это верно при любом порядке выполнения.
3. **Никаких `sleep()`.** Тест не зависит от скорости машины.

### `test_parallel_transfers_never_overdraw_the_account`
- 10 потоков × 30.00 при балансе 100.00 → `{201: 3, 422: 7}`, итог 10.00 / 90.00, 3 строки.
- **Как сломать (проверено, мутация M1):** убери `.with_for_update()` → тест падает с
  `got {201: 10}`: **все 10** переводов по 30.00 прошли при балансе 100.00. Каждый запрос прочитал
  100, вычел 30 и записал 70 — классический lost update. Деньги «напечатаны из воздуха».
- **А если убрать проверку баланса в коде (M12)?** Получим `{201: 3, 500: 7}`: в минус не ушли
  (сработал CHECK в БД), но 7 клиентов получили 500 вместо понятного `INSUFFICIENT_FUNDS`.

### `test_parallel_retries_with_same_key_debit_only_once`
- 10 одинаковых запросов с одним ключом → ровно один `201`, девять `200`, один id перевода, одна строка.
- **Интересный факт (мутация M1):** без `FOR UPDATE` этот тест **всё равно проходит** — дубли
  отсекает `UNIQUE`-ограничение в БД, лишние транзакции откатываются. Это **эшелонированная защита**
  (defense in depth). А без проверки ключа в коде (мутация M2) тест падает: клиенты получают 500.
- **Самый опасный вариант (M16):** ключ не сохраняется в БД (`idempotency_key=None`). Тогда и UNIQUE
  не помогает: результат `{201: 2, 422: 8}` — **деньги списаны дважды**. Тест это поймал.

### `test_opposite_parallel_transfers_do_not_deadlock_or_lose_money`
- 20 потоков: половина A→B, половина B→A по 1.00 → все 20 `201`, балансы по 100.00.
- **Без блокировок (M1)** тест тоже падает — из-за lost update балансы «уплывают».

## Самопроверка
1. Что такое lost update и как его предотвращает `FOR UPDATE`?
2. Почему блокировки берутся в порядке возрастания id?
3. Что доказывает первый assert в тесте атомарности (`70.00` внутри транзакции)?
4. Зачем CHECK-ограничения, если в коде уже есть проверки?
5. Почему тест «10 повторов с одним ключом» проходит даже без `FOR UPDATE`?
6. Напиши SQL, который найдёт счета с отрицательным балансом. Почему он всегда вернёт пусто?
