# 01. Python: всё, что используется в проекте

Здесь только то, что реально встречается в коде проекта. Для каждой темы — пример из проекта
и мини-задание. Запускай примеры в `python` (интерактивный режим) из активированного `.venv`.

---

## 1. Аннотации типов (type hints)

```python
def assert_status(response: httpx.Response, expected: int) -> None:
```

- `response: httpx.Response` — подсказка: «сюда передают объект ответа».
- `-> None` — функция ничего не возвращает.
- `int | None` — «число или None» (синтаксис Python 3.10+).
- `list[dict]` — список словарей.

**Важно:** Python *не проверяет* типы при запуске. Их используют IDE, линтеры и — главное
в нашем проекте — **Pydantic и FastAPI**, которые по аннотациям строят валидацию.

> Мини-задание: найди в `tests/support/api_client.py` метод, у которого параметр может быть
> `str`, `Decimal` или `None`. Как это записано?

## 2. `Decimal` — почему деньги не хранят во float

```python
>>> 0.1 + 0.2
0.30000000000000004
>>> from decimal import Decimal
>>> Decimal("0.1") + Decimal("0.2")
Decimal('0.3')
>>> Decimal(0.1)          # ловушка: создаём из float — тянем его ошибку
Decimal('0.1000000000000000055511151231257827021181583404541015625')
```

**Правило:** `Decimal` всегда создаём из **строки**. В проекте:
- в БД колонка `NUMERIC(18, 2)` (точное число, 2 знака после запятой);
- в Python — `Decimal`;
- в JSON — строка `"100.00"` (если отдать числом, JavaScript-клиент прочитает его как float).

`quantize` — округление до нужного количества знаков:
```python
>>> Decimal("100").quantize(Decimal("0.01"))
Decimal('100.00')
```
Это делает функция `_to_cents` в `app/schemas.py`.

> Мини-задание: почему тест `test_transfer_is_persisted_exactly` сравнивает
> `row["amount"] == Decimal("123.45")`, а не `== 123.45`? Проверь в консоли,
> чему равно `Decimal("123.45") == 123.45`.

## 3. f-строки

```python
f"Expected HTTP {expected}, got {describe(response)}"
f"{code!r}"          # !r — repr(): строка будет в кавычках, видно пустые строки и пробелы
f"{x:.2f}"           # форматирование числа
```

## 4. Словари и распаковка `**`

```python
VALID_REGISTRATION = {"email": "valid@example.com", "password": "...", "full_name": "Valid Name"}
payload = {**VALID_REGISTRATION, **{"email": "not-an-email"}}
# -> копия VALID_REGISTRATION, где email заменён
```
Используется в `test_register_with_invalid_payload_returns_422`: берём валидные данные и ломаем
**одно** поле — так при падении сразу понятно, в чём причина.

Множества (`set`) и операции над ними:
```python
assert not {"password", "password_hash"} & body.keys()   # & — пересечение
```

## 5. List comprehension

```python
error_fields = [err["loc"][-1] for err in body["errors"]]
listed = {a["id"] for a in response.json()}        # set comprehension
```
Читается как: «для каждого `err` из `body["errors"]` взять `err["loc"][-1]`».

## 6. Функции как объекты, `lambda`

```python
pytest.param(lambda u: f"Basic {u.token}", ..., id="wrong-scheme")
```
`lambda u: ...` — короткая безымянная функция. В тесте токенов параметр — *функция*, которая
строит заголовок, потому что пользователь (`u`) создаётся фикстурой уже во время теста.

`getattr(obj, "name")` — получить метод по имени-строке (см. `test_foreign_account_...`).

## 7. Замыкания и фабрики

```python
@pytest.fixture
def account_factory():
    def create(owner, balance="0.00", currency="KZT"):
        ...
    return create
```
Фикстура возвращает **функцию**. Тест вызывает её сколько угодно раз с разными параметрами.
Это паттерн «фабрика» — один из самых полезных в pytest.

## 8. `@dataclass`

```python
@dataclass
class TestUser:
    id: int
    email: str
    ...
```
Декоратор сам создаёт `__init__`, `__repr__`, `__eq__`. Удобно для «контейнеров данных».
`__test__ = False` — говорит pytest: «это не тестовый класс», хотя имя начинается с `Test`.

## 9. Декораторы

```python
@router.post("/auth/register", status_code=201)
def register(...): ...

@pytest.mark.parametrize(...)
def test_...(...): ...
```
Декоратор — функция, которая принимает функцию и возвращает изменённую/зарегистрированную.
FastAPI так регистрирует эндпоинты, pytest — метки и параметры.

## 10. Контекстные менеджеры `with`

```python
with Session(db_engine) as session, pytest.raises(RuntimeError, match="simulated crash"):
    ...
with engine.connect() as conn: ...
```
`with` гарантирует «закрыть/откатить», даже если внутри было исключение.
`pytest.raises` — тоже контекстный менеджер: тест падает, если исключение **не** возникло.

## 11. Генераторы и `yield` в фикстурах

```python
@pytest.fixture
def anon_api(base_url):
    api = FinGuardApi(base_url)
    yield api          # <- отдали тесту, ждём окончания теста
    api.close()        # <- teardown: выполнится после теста, даже если он упал
```

## 12. Исключения

```python
try:
    db.commit()
except IntegrityError:
    db.rollback()
    raise AppError(409, "EMAIL_TAKEN", "...") from None
```
`raise ... from None` — скрыть исходное исключение из трейсбэка (оно здесь ожидаемое).

## 13. Потоки: `threading.Barrier` и `ThreadPoolExecutor`

```python
barrier = threading.Barrier(10)
def worker(i):
    barrier.wait()          # все 10 потоков ждут здесь, затем стартуют ОДНОВРЕМЕННО
    return api.transfer(...)
with ThreadPoolExecutor(max_workers=10) as pool:
    responses = list(pool.map(worker, range(10)))
```
Это основа конкурентных тестов (подробно — в `04_sql_testing_ru.md`).

## 14. `Counter`

```python
>>> from collections import Counter
>>> Counter([201, 422, 422, 201, 422])
Counter({422: 3, 201: 2})
>>> Counter([201, 422, 422]) == {201: 1, 422: 2}
True
```

## 15. Модули и пакеты

`tests/__init__.py` делает папку пакетом, поэтому работает `from tests.support.db import DbInspector`.
`pip install -e .` ставит пакет `app` в режиме «editable»: изменения в коде видны сразу.

---

## Самопроверка

1. Почему `Decimal(0.1) != Decimal("0.1")`?
2. Что выведет `{**{"a": 1, "b": 2}, **{"b": 3}}`?
3. Чем фикстура с `return` отличается от фикстуры с `yield`?
4. Зачем `Barrier`, если можно просто запустить 10 потоков?
5. Что делает `!r` в f-строке и почему он полезен в сообщениях об ошибках?
