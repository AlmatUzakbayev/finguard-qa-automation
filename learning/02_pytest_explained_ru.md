# 02. pytest: как устроен тестовый фреймворк проекта

## 1. Как pytest находит тесты

- Папки из `testpaths = ["tests"]` (`pyproject.toml`).
- Файлы `test_*.py`, функции `test_*`.
- `conftest.py` — специальный файл: фикстуры из него доступны всем тестам в этой папке и ниже.
  Его **не импортируют** — pytest подключает его сам.

```
tests/conftest.py        <- общие фикстуры: сервер, БД, пользователи, счета (для API и UI)
tests/ui/conftest.py     <- только для UI: logged_in_page, таймаут expect
```

## 2. Фикстуры — подготовка данных и окружения

Фикстура — функция с `@pytest.fixture`. Тест «просит» фикстуру, указав её имя как параметр:

```python
def test_deposit_increases_balance(user, account_factory):
```
pytest видит параметры `user` и `account_factory`, находит фикстуры с такими именами,
выполняет их и передаёт результат в тест. Это называется **dependency injection**.

### Цепочка фикстур для одного теста

Для `test_deposit_increases_balance(user, account_factory)`:

```
user ──► user_factory ──► base_url ──► db_engine
                                 (проверка БД, миграции, запуск uvicorn — 1 раз за сессию)
account_factory  (просто возвращает функцию create)
```

### scope — сколько живёт фикстура

| scope | Когда создаётся | В проекте |
|---|---|---|
| `function` (по умолчанию) | для каждого теста заново | `user`, `anon_api`, `account_factory` |
| `session` | один раз на весь запуск | `db_engine`, `base_url` (сервер дорого запускать) |

**Почему пользователь — function, а сервер — session?** Сервер запускается ~10–25 секунд, и он
не хранит состояние между тестами. А пользователь — это данные: если тесты делят одного пользователя,
один тест может испортить данные другому (например, потратить баланс). Отсюда правило: **данные —
свежие на каждый тест, инфраструктура — общая**.

### yield-фикстуры (setup / teardown)

```python
@pytest.fixture(scope="session")
def base_url(db_engine):
    ... запускаем сервер ...
    yield url              # тесты работают
    proc.terminate()       # после всех тестов сервер останавливается
```

### Фабрики

`user_factory`, `account_factory` возвращают функцию. Нужен второй пользователь? `user_factory()`
ещё раз. Нужен счёт с балансом 1000? `account_factory(user, balance="1000.00")`.

## 3. Изоляция тестов

Каждый тест создаёт **своих** пользователей с уникальным email (`uuid`). Поэтому:
- тесты можно запускать в любом порядке и по одному;
- не нужно чистить БД между тестами;
- тесты можно распараллелить (`pytest-xdist`) без переделки.

> Как проверить изоляцию: `pytest tests/api -p no:randomly` и в обратном порядке
> (`pip install pytest-reverse`, `pytest --reverse`). Результат должен совпасть.

## 4. parametrize — один тест, много наборов данных

```python
@pytest.mark.parametrize(
    "amount",
    [
        pytest.param("-10.00", id="negative"),
        pytest.param("0", id="zero"),
        ...
    ],
)
def test_transfer_with_invalid_amount_is_rejected_and_changes_nothing(user, account_factory, db, amount):
```
- Тест запустится 7 раз, по разу на каждое значение.
- `id="negative"` — имя кейса в отчёте: `test_transfer_with_invalid_amount...[negative]`.
  Без `id` было бы `[-10.00]` — для чисел нормально, для словарей — нечитаемо.
- Несколько параметров: `("balance", "amount", "expected_status")` + список кортежей.

**Когда parametrize, а когда отдельный тест?** Если шаги одинаковые и меняются только данные и
ожидаемый результат — parametrize. Если шаги разные — отдельные тесты.

## 5. Маркеры (markers)

```python
@pytest.mark.smoke
@pytest.mark.negative
```
Объявлены в `pyproject.toml` (`--strict-markers` запрещает опечатки вроде `@pytest.mark.smok`).
Запуск по маркерам:
```bash
pytest -m smoke
pytest -m "negative and not concurrency"
pytest -m "db or concurrency"
```

## 6. Assertions и понятные сообщения

pytest переписывает `assert`, чтобы показать значения:
```
>       assert response.status_code == 201
E       assert 422 == 201
```
Видно «что», но не видно «почему». Поэтому в проекте есть `tests/support/assertions.py`:
```
E   AssertionError: Expected HTTP 201, got POST /api/transfers -> 422:
E   {"code":"INSUFFICIENT_FUNDS","detail":"Insufficient funds on the source account"}
```
Сразу ясно, какой запрос, какой ответ и почему.

Второй аргумент assert — сообщение:
```python
assert len(rows) == 1, f"Expected exactly one transaction row, got {rows}"
```

## 7. monkeypatch — подмена кода в тесте

```python
monkeypatch.setattr(services, "_record_transfer", crash_while_recording)
```
На время теста функция `_record_transfer` заменяется на нашу, которая падает. После теста
pytest **автоматически** вернёт оригинал. Используется в тесте атомарности.

## 8. pytest.raises

```python
with pytest.raises(IntegrityError, match="ck_accounts_balance_non_negative"):
    conn.execute(text("UPDATE accounts SET balance = -0.01 ..."))
```
Тест **падает**, если исключения не было, или оно другого типа, или текст не совпал с `match`.

## 9. Плагины проекта

| Плагин | Зачем |
|---|---|
| `pytest-playwright` | фикстуры `page`, `browser`; опции `--headed`, `--browser`, скриншоты/трассировки |
| `pytest-html` | HTML-отчёт: `--html=reports/report.html --self-contained-html` |
| `pytest-timeout` | `--timeout=120`: зависший тест падает со стектрейсом, а не вешает CI навсегда |

## 10. Полезные команды

```bash
pytest tests/api/test_transfers.py                       # один файл
pytest tests/api/test_transfers.py::test_transfer_moves_money_between_users   # один тест
pytest -k "idempotency and not parallel"                  # по подстроке имени
pytest -x                                                 # остановиться на первом падении
pytest --lf                                               # перезапустить только упавшие
pytest -v                                                 # подробный вывод
pytest -s                                                 # показывать print()
pytest --pdb                                              # открыть отладчик в месте падения
pytest --durations=10                                     # 10 самых медленных
pytest --collect-only -q                                  # список тестов без запуска
```

## 11. Как отлаживать упавший тест — алгоритм

1. Прочитай **последнюю** строку ошибки (`E   AssertionError: ...`) — что ожидали и что получили.
2. Посмотри на тело ответа в сообщении (`-> 422: {...}`): код ошибки обычно объясняет причину.
3. Посмотри `reports/server.log` — логи сервера (каждый запрос и трейсбэк при 500).
4. Запусти один тест с `-v -s`, добавь `print(response.json())`.
5. `pytest --pdb` → в отладчике: `p response.json()`, `p db.balance(source["id"])`.
6. Для UI — открой trace (см. `05_playwright_ru.md`).
7. Определи: это баг в **тесте** или в **приложении**? Проверь вручную через Swagger (`/docs`).

## Самопроверка

1. Какие фикстуры и в каком порядке выполнятся для `test_cannot_transfer_from_someone_elses_account`?
2. Что будет, если сделать `user` фикстурой со `scope="session"`? Какие тесты могут начать падать?
3. Зачем `--strict-markers`?
4. Сколько раз выполнится `test_transfer_amount_boundaries` и как называется каждый запуск?
5. Как запустить только UI-тесты на проверку ошибок формы перевода?
