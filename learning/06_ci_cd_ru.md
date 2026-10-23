# 06. CI/CD, Docker, Ruff и локальный запуск

## 1. Локальный запуск — два варианта

### Вариант А: Docker (рекомендуется)
```bash
docker compose up -d db          # поднимает PostgreSQL 16 и создаёт БД finguard и finguard_test
python -m venv .venv
.venv\Scripts\activate           # Windows (Linux/macOS: source .venv/bin/activate)
pip install -e ".[test]"
python -m playwright install chromium
pytest
```

### Вариант Б: без Docker (так проект разрабатывался)
На машине разработки Docker не было. Использовался «портативный» PostgreSQL 16 (zip-архив без установки):
```bash
# initdb создаёт каталог данных; pg_ctl запускает сервер
pgsql/bin/initdb -D data -U postgres --pwfile=pw.txt -E UTF8 --locale=C -A scram-sha-256
pgsql/bin/pg_ctl -D data -o "-p 5432" -l pg.log start
pgsql/bin/psql -U postgres -h localhost -c "create database finguard;" -c "create database finguard_test;"
```
После перезагрузки компьютера сервер нужно снова запустить командой `pg_ctl ... start`.

## 2. Что происходит при `pytest` (tests/conftest.py)

1. `db_engine` — подключается к `TEST_DATABASE_URL`. Нет БД → понятная ошибка и выход (код 3).
2. `base_url` — выполняет `alembic upgrade head` (миграции), запускает `uvicorn` на свободном порту,
   ждёт `GET /health == 200` (до 30 с).
3. Тесты.
4. Сервер останавливается. Лог сервера — в `reports/server.log`.

Если задан `API_BASE_URL` — шаги 2 и 4 пропускаются, тесты идут на указанный сервер.

## 3. Миграции (Alembic)

Миграция — версия схемы БД в виде кода (`alembic/versions/0001_initial_schema.py`).
```bash
alembic upgrade head        # применить все миграции
alembic downgrade -1        # откатить последнюю
alembic current             # текущая версия БД
```
**Почему не `Base.metadata.create_all()`?** В реальных проектах схема меняется со временем,
данные нужно сохранить. Миграции — это история изменений, которую можно применить к любой БД.

## 4. GitHub Actions — разбор `.github/workflows/ci.yml`

```yaml
on:
  push:
  pull_request:
  workflow_dispatch:        # кнопка «Run workflow» вручную
```
Когда запускается.

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```
Новый push в ту же ветку отменяет старый запуск — экономия времени.

**Job `lint`** — `ruff check .` и `ruff format --check .`. Быстрый, отдельный: стиль кода
проверяется независимо от тестов.

**Job `tests`:**
```yaml
services:
  postgres:
    image: postgres:16-alpine
    options: --health-cmd "pg_isready -U postgres" ...
```
GitHub запускает PostgreSQL в Docker-контейнере рядом с job. `health-cmd` — шаги начнутся,
только когда база готова принимать подключения.

```yaml
- run: python -m playwright install --with-deps chromium
```
`--with-deps` ставит системные библиотеки Linux, нужные браузеру.

```yaml
- name: UI tests
  if: success() || failure()
```
UI-тесты запускаются, даже если API-тесты упали, — чтобы видеть картину целиком.
(По умолчанию шаг после упавшего шага пропускается.)

```yaml
- uses: actions/upload-artifact@v4
  if: always()
  with:
    path: reports/
```
Отчёты, лог сервера, скриншоты и трассировки сохраняются **всегда**, а особенно — при падении.
Их можно скачать на странице запуска (раздел Artifacts).

`JWT_SECRET` в workflow — одноразовое значение только для тестового сервера в CI, оно ничего не
защищает. Настоящие секреты хранят в **Settings → Secrets** и используют как `${{ secrets.NAME }}`.

## 5. Как запустить CI в первый раз (сделать самому)

```bash
git init                              # если ещё не сделано
git add . && git commit -m "Initial commit"
# На github.com: New repository → finguard-qa-automation (без README)
git remote add origin https://github.com/<твой-логин>/finguard-qa-automation.git
git branch -M main
git push -u origin main
```
Дальше: вкладка **Actions** → запуск **CI** → дождаться результата.
**Пока CI не стал зелёным на GitHub, в резюме нельзя писать «настроен CI».** Если что-то
упало — скачай артефакт `test-reports`, открой `server.log` и HTML-отчёт.

Бейдж для README (после первого успешного запуска):
```markdown
![CI](https://github.com/<логин>/finguard-qa-automation/actions/workflows/ci.yml/badge.svg)
```

## 6. Ruff

Ruff — линтер и форматтер (замена flake8 + isort + black, написан на Rust, очень быстрый).
```bash
ruff check .            # найти проблемы
ruff check --fix .      # исправить автоматически, что можно
ruff format .           # отформатировать код
```
Правила (`pyproject.toml`, `[tool.ruff.lint] select`): `E/W` стиль, `F` ошибки (неиспользуемые
импорты), `I` порядок импортов, `B` частые баги, `UP` современный синтаксис, `PT` стиль pytest,
`SIM` упрощения.

Пример реальной находки Ruff в проекте: `PT018` — «разбей assert на несколько». Было
`assert isinstance(x, str) and x` — при падении непонятно, какая часть неверна. Стало два assert.

## 7. Docker Compose

`docker-compose.yml`: сервис `db` (PostgreSQL) и `app` (наш сервис, собирается из `Dockerfile`).
`depends_on: condition: service_healthy` — приложение стартует после того, как БД готова.
`docker/init-test-db.sql` выполняется при первом создании контейнера и создаёт `finguard_test`.

```bash
docker compose up -d --build     # всё
docker compose logs -f app       # логи приложения
docker compose down -v           # остановить и удалить данные (-v удаляет volume)
```
> **Честно:** на машине разработки Docker не установлен, поэтому `docker compose` не запускался.
> Это первое, что стоит проверить у себя.

## Типичные проблемы

| Симптом | Причина | Что делать |
|---|---|---|
| `PostgreSQL is not reachable` | БД не запущена / другой порт | `docker compose up -d db` или `pg_ctl start`; проверь `TEST_DATABASE_URL` |
| `Server did not become healthy` | приложение упало при старте | открой `reports/server.log` |
| `Executable doesn't exist ... chromium` | не установлен браузер | `python -m playwright install chromium` |
| Все запросы медленные на Windows (~2 с) | `localhost` сначала пробует IPv6 | используй `127.0.0.1` (так сделано в проекте) |
| CI: тесты зелёные локально, красные в CI | разные версии/окружение | смотри артефакты; сравни версию Python (CI — 3.12) |

## Самопроверка
1. Зачем в CI отдельный job для Ruff?
2. Что произойдёт с артефактами, если упадёт шаг «API tests»?
3. Чем `alembic upgrade head` лучше `create_all()`?
4. Где хранить настоящий секрет для CI?
