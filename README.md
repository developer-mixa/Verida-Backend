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
│       └── system/          # Служебные эндпоинты (hello, позже — расширения)
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
| `users` | `email`, `number`, `username` — все NOT NULL и уникальны; `password_hash`, `role_id` → `roles`, `is_verified`. |
| `articles` | `user_id` → `users`, `title`, длинный `content` (TEXT). |
| `tags` | Каталог тегов: `article_type`, `article_name`. |
| `article_tags` | Связка M–N `articles` ↔ `tags` (составной PK). |
| `article_questions` | Вопрос–ответ по статье: `article_id`, `question`, `answer` (TEXT). |

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

```bash
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
