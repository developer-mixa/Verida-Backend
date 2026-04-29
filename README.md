# Verida-Backend

HTTP API для мобильного клиента **Verida** ([scientific_chat_app](../scientific_chat_app/README.md)): изучение материалов статей, ответы в научном стиле, заметки, закрепление, профиль. Клиент обращается к API по базовому URL с префиксом `/api` (см. мобильный `api_endpoints.dart`).

## Стек

| Категория | Технология |
|-----------|------------|
| Язык / фреймворк | Python 3.10+ (рекомендуется 3.12 в Docker), FastAPI |
| БД | PostgreSQL 16 |
| ORM / миграции | SQLAlchemy 2 (async), Alembic |
| Контейнеры | Docker, docker-compose |

## Архитектура репозитория

```
Verida-Backend/
├── app/
│   ├── main.py              # Сборка приложения, include_router
│   ├── core/                # Конфиг, БД, ORM-модели (`models/`), константы сидов
│   └── features/            # Изолированные фичи
│       ├── auth/            # Регистрация, вход, JWT
│       ├── articles/        # Чтение статей пользователя (список, детали)
│       └── system/          # Служебные эндпоинты (hello)
├── alembic/                 # Миграции
├── tests/                   # Зеркало структуры: tests/features/<фича>/
├── scripts/                 # entrypoint и вспомогательные скрипты
├── docker-compose.yml       # Прод-подобный запуск: API + БД (порт БД наружу не открыт)
└── docker-compose.local-db.yml   # Только PostgreSQL с портом 5432 на хосте
```

**Правило изоляции:** `app/features/<A>/` **не** импортирует модули из `app/features/<B>/`. Общее — в `app/core/`.

ORM-модели лежат в `app/core/models/`, чтобы таблицы и связи не тянули импорты между фичами; репозитории фич используют только `core` и свою фичу.

## Схема БД (актуальная)

| Таблица | Назначение |
|---------|------------|
| `roles` | Роли: сид `user`, `premium_user`, `admin` (фиксированные UUID в `app/core/constants.py` и миграции `0002_schema_domain`). |
| `users` | `username` NOT NULL, уникален; `email` и/или `number` (телефон) — уникальны, nullable, **хотя бы одно** задано; `password_hash`, `role_id` → `roles`, `is_verified`. |
| `articles` | `user_id` → `users`, `title`, `content` (TEXT); опционально `chat_session_id` → `chat_sessions`; `parent_id` → `articles` (иерархия, `ON DELETE CASCADE`); `is_folder` (узел-папка). Миграция `0006_articles_parent_and_folder`. |
| `chat_sessions` | Тема чата: `user_id`, `title`, `created_at` / `updated_at`, `archived_at`, `active_article_id` → `articles` (текущий конспект). Миграция `0004_ai_chat_tables`. |
| `chat_messages` | Сообщения в теме: `session_id`, `role`, `content`, `payload` (JSONB). |
| `tags` | Каталог тегов: `article_type`, `article_name`. |
| `article_tags` | Связка M–N `articles` ↔ `tags` (составной PK). |
| `article_questions` | Вопрос–ответ по статье: `article_id`, `question`, `answer` (TEXT). |

## Список эндпоинтов (полный перечень)

Используйте как справочник для клиента (`scientific_chat_app`). **Обновляйте таблицу при добавлении новых роутов.**

Базовый URL приложения: `http(s)://<хост>:<порт>` (например `http://127.0.0.1:8080`). Прикладные маршруты живут под префиксом **`/api`**; служебные и документация — **без** `/api`.

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | Проверка живости (JSON `{"status":"ok"}`). |
| `GET` | `/docs` | Интерактивная документация Swagger (OpenAPI). |
| `GET` | `/redoc` | Документация ReDoc. |
| `GET` | `/openapi.json` | Схема OpenAPI 3 (для кодогена / Postman). |
| `GET` | `/api/system/hello` | Тестовый ответ (`{"message":"Hello from Verida-Backend"}`). |
| `POST` | `/api/auth/register` | Регистрация. Тело JSON: `username` (обяз.), `email` и/или `phone` (хотя бы одно), `password` (8–72 символа). Ответ `201`: `access_token`, `token_type` (`bearer`). |
| `POST` | `/api/auth/login` | Вход. Тело JSON: `contact` (username **или** email **или** телефон), `password`. Ответ `200`: `access_token`, `token_type`. |
| `POST` | `/api/chat/sessions` | Создать тему чата. Тело: опционально `title`. Ответ `201`: `id`, `title`, `created_at`. |
| `POST` | `/api/chat/sessions/{session_id}/messages/stream` | Сообщение в тему; ответ **SSE** (`text/event-stream`), события JSON в `data:` (`session`, `delta`, `error`, `done`). Сообщения пишутся в БД. Требуется **JWT** и переменные **Yandex GPT** (см. `.env.example`). |
| `POST` | `/api/chat/sessions/{session_id}/synopsis` | **Только по этому запросу** создаётся/обновляется статья-конспект в `articles` (не при каждом сообщении в чате). LLM обязан вызвать `save_synopsis` → upsert одной статьи на тему и теги в `article_tags`. Ответ `200`: `article_id`, `updated`, `title`, `tags`. Пустой диалог — `422`; нет сессии — `404`; ошибка LLM — `502`. **JWT** обязателен. |
| `GET` | `/api/articles` | Список статей: `id`, `title`, `chat_session_id`, `parent_id`, `is_folder`, `tags`. Query: `limit`, `offset`; опционально `parent_id` (только дети) или `roots_only=true` (только корень); вместе нельзя. **JWT** обязателен. |
| `POST` | `/api/articles/import-zip` | `multipart/form-data`, поле `file` — ZIP с `.md` и вложенными папками; пути в БД не хранятся. Ответ `201`: `created_count`, `root_article_ids`. Нет `.md` или неверный архив — `400`. **JWT** обязателен. |
| `GET` | `/api/articles/{article_id}` | Детали: `title`, `content`, `chat_session_id`, `parent_id`, `is_folder`, `tags`. Только своя статья — иначе `404`. **JWT** обязателен. |

**Интернет и литература (чат):** **Yandex Responses API** + один нативный **`web_search`** в `tools` (два `web_search` в одном запросе API отклоняет с 400). По умолчанию поиск по всему интернету с `search_context_size: high`; модель в инструкции ориентирована сначала на научные формулировки запроса, затем на более широкие. Опционально: `YANDEX_WEB_SEARCH_REGION`, `YANDEX_WEB_SEARCH_ONLY_SCIENCE_DOMAINS=1` — ограничить выдачу научными доменами из кода. Длинная история чата **обрезается с конца бюджета токенов** (`YANDEX_CHAT_MAX_DIALOGUE_TOKENS`, по умолчанию 14000), иначе провайдер может вернуть ошибку по лимиту 32768 с учётом web_search. Конспект (`/synopsis`) — **chat.completions** + только `save_synopsis`, без веб-поиска.

Ошибки: валидация — `422`; конфликт (занят username/email/телефон) — `409` на регистрации; неверный логин/пароль — `401` на входе.

**JWT:** секрет подписи — `JWT_SECRET_KEY` в `.env` (≥ 32 символов), см. [.env.example](.env.example). Заголовок: `Authorization: Bearer <access_token>`. Маршруты `/api/chat/*` и чтение `/api/articles` / `/api/articles/{id}` требуют JWT.

**Правило для агента и разработчиков:** см. [.cursor/rules/verida-backend.mdc](.cursor/rules/verida-backend.mdc) — чистый код по фичам, тесты, документация и Swagger на фичу, миграции только через Alembic; фича с ИИ оставлена для самостоятельной работы владельца.

## Быстрый старт (локально, hot reload)

1. Поднять только БД с портом на хосте:

   ```bash
   docker compose -f docker-compose.local-db.yml up -d
   ```

2. Создать виртуальное окружение, установить зависимости:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. Скопировать переменные окружения и применить миграции:

   ```bash
   cp .env.example .env
   .venv/bin/alembic upgrade head
   ```

   Важно вызывать **Alembic из виртуального окружения** (`.venv/bin/alembic` или `source .venv/bin/activate` и затем `alembic`). Если в терминале первым в `PATH` стоит системный `/usr/bin/alembic` (пакет Debian), подтянется чужой Python без зависимостей проекта — типичная ошибка: `ModuleNotFoundError: No module named 'pydantic_settings'`.

4. Запустить FastAPI с перезагрузкой при изменении кода:

   ```bash
   .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
   ```

Проверка: [http://127.0.0.1:8080/health](http://127.0.0.1:8080/health), [http://127.0.0.1:8080/api/system/hello](http://127.0.0.1:8080/api/system/hello), Swagger: [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs).

## Прод-подобный запуск (Docker)

API и PostgreSQL в одной сети; **порт PostgreSQL наружу не публикуется** (только `api` на `8080`).

Учётные данные БД и строка `DATABASE_URL` для контейнера `api` **не зашиты в `docker-compose.yml`**: задаются в `.env` (скопируйте из [.env.example](.env.example)). В `DATABASE_URL` для этого сценария хост БД — **`db`** (имя сервиса в сети compose), логин/пароль/имя БД должны совпадать с `POSTGRES_*`.

```bash
cp .env.example .env
# выставить POSTGRES_PASSWORD и строку DATABASE_URL с хостом db
docker compose up --build -d
```

Миграции выполняются в `entrypoint` перед стартом `uvicorn`.

## Миграции

```bash
# новая ревизия (после добавления моделей и импорта в alembic/env.py)
.venv/bin/alembic revision --autogenerate -m "описание"

# применить
.venv/bin/alembic upgrade head
```

Эквивалентно при активированном venv: `source .venv/bin/activate`, затем `alembic ...`.

## Тесты

```bash
.venv/bin/pytest
```

## Переменные окружения

См. [.env.example](.env.example). Главное — `DATABASE_URL` с драйвером `postgresql+asyncpg://...` для приложения; Alembic сам переводит URL на синхронный `psycopg` в `app/core/config.py`.
