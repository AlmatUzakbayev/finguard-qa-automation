# 05. Playwright и UI-автоматизация

## 1. Что такое Playwright и чем он хорош

Playwright управляет настоящим браузером (Chromium, Firefox, WebKit). Главное отличие от
классического Selenium — **автоожидание**: перед кликом он сам ждёт, пока элемент появится,
станет видимым, активным и перестанет двигаться. Поэтому в тестах **нет `sleep()`**.

```bash
pytest tests/ui                         # headless (без окна)
pytest tests/ui --headed --slowmo 500   # видно браузер, каждое действие с паузой 0.5 с
pytest tests/ui --browser firefox       # другой браузер (нужно: playwright install firefox)
PWDEBUG=1 pytest tests/ui -k logout     # Playwright Inspector: пошаговое выполнение
```

## 2. Локаторы

```python
page.get_by_test_id("login-button")        # data-testid="login-button"  <- основной способ в проекте
page.get_by_role("button", name="Sign in") # по роли и доступному имени
page.get_by_text("Welcome")                # по тексту
page.locator("[data-testid^=account-row-]")# CSS-селектор
```
**Почему `data-testid`:** не ломается, когда меняют текст кнопки, CSS-классы или вёрстку.
Это договорённость с разработчиками: «этот атрибут — для тестов, не трогайте».

Локатор **ленивый**: `page.get_by_test_id("x")` ничего не ищет, пока с ним не сделали действие
или проверку. Поэтому локатор можно создать заранее (в Page Object).

## 3. Проверки `expect` — с ожиданием

```python
expect(transfer.success).to_contain_text("120.75 sent to account #5")
expect(page).to_have_url(re.compile(r"/dashboard\.html$"))
expect(history.rows).to_have_count(2)
expect(transfer.error).to_be_hidden()
```
`expect` **повторяет** проверку, пока она не станет истинной или не истечёт таймаут
(в проекте 10 с, `tests/ui/conftest.py`). Сравни:

```python
assert transfer.success.text_content() == "..."   # ПЛОХО: проверит один раз, мгновенно,
                                                  # текст ещё может не появиться -> flaky
expect(transfer.success).to_have_text("...")      # ХОРОШО: подождёт
```

## 4. Page Object Model (tests/ui/pages.py)

Класс на каждую страницу: **локаторы + действия**. Тест описывает **что** делает пользователь,
Page Object знает **как**.

```python
class TransferPage(BasePage):
    path = "/transfer.html"

    @property
    def error(self) -> Locator:
        return self.by_testid("transfer-error")

    def send(self, from_id, to_id, amount, description=""):
        self.fill(from_id, to_id, amount, description)
        self.submit_button.click()
```
Тест:
```python
transfer = TransferPage(logged_in_page).open()
transfer.send(source["id"], target["id"], "120.75", description="Books")
expect(transfer.success).to_contain_text("120.75 sent")
```
**Где POM действительно помогает:** форма перевода используется в 3 тестах (7 запусков). Если
изменится поле суммы — правка в одном месте.
**Где не переусложняем:** нет отдельных классов для таблиц, кнопок и т.п. — это было бы лишним.
**Assert-ы — в тестах, не в Page Object.** Page Object не решает, что правильно.

## 5. Подготовка данных через API

```python
def test_dashboard_shows_balance_of_each_account(user, account_factory, page):
    kzt = account_factory(user, balance="15000.50")      # через API — быстро и надёжно
    LoginPage(page).open().login(user.email, user.password)   # через UI — то, что проверяем
    expect(dashboard.balance_of(kzt["id"])).to_have_text("15000.50 KZT")
```
Через UI проверяем **только то, что тестирует этот тест**. Создавать 2 счёта через форму в
каждом тесте — медленно, и тест упадёт из-за формы счетов, хотя проверяет дашборд.

После UI-действия результат проверяется ещё и **через API** (кросс-проверка):
```python
assert user.api.get_balance(source["id"]).json()["balance"] == "379.25"
```
Экран может показывать одно, а в базе — другое.

## 6. Изоляция

Фикстура `page` (pytest-playwright) создаёт **новый browser context** на каждый тест —
как новый профиль в режиме инкогнито: нет cookies, нет `sessionStorage`. Поэтому тест logout не
влияет на следующий тест.

## 7. Скриншоты и трассировка при падении

В `pyproject.toml`:
```
--screenshot=only-on-failure --tracing=retain-on-failure --output=reports/playwright
```
При падении в `reports/playwright/<имя-теста>/` появятся `test-failed-1.png` и `trace.zip`.
```bash
python -m playwright show-trace reports/playwright/<имя-теста>/trace.zip
```
Trace Viewer показывает каждое действие: снимок DOM до/после, сетевые запросы, консоль браузера.
Это лучший инструмент диагностики UI-тестов. В CI эти файлы сохраняются как артефакты.

## 8. Разбор UI-тестов

### `test_login_with_valid_credentials_opens_dashboard`
- **Сценарий:** вход через форму. **Ожидание:** URL `/dashboard.html`, «Welcome, <имя>», имя в шапке.
- **Как сломать:** в `frontend/login.html` замени `location.assign("/dashboard.html")` на
  `"/accounts.html"` → упадёт проверка URL.

### `test_protected_page_redirects_anonymous_user_to_login` (4 кейса)
- Открываем защищённые страницы без входа → должен быть редирект на логин.
- **Как сломать:** в `frontend/app.js` в `requireAuth` закомментируй `location.replace("/login.html")`.
- **Важно понимать:** это защита **интерфейса**, а не данных. Данные защищает API (401), что
  проверяют API-тесты. UI-проверка — про удобство пользователя.

### `test_logout_ends_the_session`
- После «Sign out» видим сообщение, а повторное открытие дашборда ведёт на логин.
- **Как сломать:** в `requireAuth` в обработчике logout убери `session.clear()` → редирект на логин
  произойдёт, но токен останется; повторное открытие дашборда **не** вернёт на логин → тест упадёт.
- **Ограничение (known_issues):** токен на сервере остаётся валидным до истечения срока.

### `test_transfer_form_shows_validation_errors` (5 кейсов)
| Кейс | Где ловится ошибка | Текст |
|---|---|---|
| missing-recipient | в браузере (JS) | Enter the destination account number. |
| missing-amount | в браузере (JS) | Enter an amount. |
| zero-amount | на сервере (422) | amount: Input should be greater than or equal to 0.01 |
| three-decimals | на сервере (422) | amount: Decimal input should have no more than 2 decimal places |
| insufficient-funds | на сервере (422) | Insufficient funds on the selected account. |

Тест проверяет и **отсутствие** сообщения об успехе, и неизменный баланс через API.

### `test_double_click_on_send_creates_only_one_transfer`
- Двойной клик по «Send money» → ровно **один** перевод.
- **Две линии защиты:** (1) кнопка блокируется на время запроса; (2) форма отправляет один и тот же
  `Idempotency-Key`, пока перевод не завершён.
- **Проверено мутациями:** убрали только блокировку кнопки (M9) — тест **прошёл**: защитил ключ
  идемпотентности. Убрали обе защиты (M10) — тест **упал**. Вывод: тест проверяет *результат для
  пользователя* («не списали дважды»), а не конкретный механизм. Это хорошо: тест не мешает
  менять реализацию.

### `test_history_shows_transfer_for_sender_and_receiver`
- Отправитель видит `-45.00` с описанием и номером получателя; получатель — `+45.00`.
- `history.rows.first` — первая строка (новые сверху).

## 9. Частые причины нестабильных (flaky) UI-тестов и как они решены

| Причина | Решение в проекте |
|---|---|
| `sleep(2)` вместо ожидания | `expect(...)` с автоожиданием |
| Хрупкие селекторы (`div > div:nth-child(3)`) | `data-testid` |
| Зависимость от данных других тестов | свежий пользователь + новый browser context |
| Опции `<select>` грузятся асинхронно | `select_option` ждёт появления опции |
| Проверка до завершения запроса | ждём сообщения об успехе / активной кнопки |

## 10. Наблюдение из разработки проекта

Один раз полный прогон UI-тестов завис (без ошибок) на этапе между тестами и не воспроизвёлся при
повторе. Решение — `pytest-timeout` (`--timeout=120`): зависший тест падает со стектрейсом, а CI
не висит часами. Честно записано в отчёт: причина не установлена.

## Самопроверка
1. Почему `expect(...).to_have_text()` надёжнее, чем `assert locator.text_content() == ...`?
2. Зачем создавать данные через API в UI-тесте?
3. Защищает ли редирект на логин данные пользователя? Что их защищает?
4. Почему тест двойного клика не упал, когда убрали блокировку кнопки? Это плохой тест?
5. Где искать trace упавшего теста и что в нём есть?
