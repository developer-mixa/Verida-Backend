from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import PurePosixPath

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.articles.repositories.article_repository import ArticleRepository

MAX_ZIP_BYTES = 12 * 1024 * 1024
MAX_MEMBERS = 600
MAX_DECOMPRESSED_TOTAL = 40 * 1024 * 1024
MAX_SINGLE_FILE = 8 * 1024 * 1024
MAX_PATH_DEPTH = 48


class ZipImportError(Exception):
    """Ошибка валидации или разбора ZIP (сообщение для HTTP 400)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _safe_parts(name: str) -> tuple[str, ...] | None:
    name = name.strip().replace("\\", "/").lstrip("/")
    if not name:
        return None
    p = PurePosixPath(name)
    parts: list[str] = []
    for part in p.parts:
        if part == "..":
            return None
        if part.startswith("__MACOSX"):
            return None
        if part == ".DS_Store":
            return None
        parts.append(part)
    if not parts:
        return None
    if len(parts) > MAX_PATH_DEPTH:
        return None
    return tuple(parts)


def _folder_keys_from_parent_dir(parent_dir: tuple[str, ...]) -> list[tuple[str, ...]]:
    return [parent_dir[:i] for i in range(1, len(parent_dir) + 1)]


async def import_articles_from_zip(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    zip_bytes: bytes,
) -> tuple[int, list[uuid.UUID]]:
    if len(zip_bytes) > MAX_ZIP_BYTES:
        raise ZipImportError("Архив слишком большой")

    root_ids: list[uuid.UUID] = []
    created = 0

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise ZipImportError("Некорректный ZIP-файл") from e

    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ZipImportError("Слишком много записей в архиве")

        total_declared = sum(min(i.file_size, MAX_SINGLE_FILE) for i in infos)
        if total_declared > MAX_DECOMPRESSED_TOTAL:
            raise ZipImportError("Суммарный размер содержимого архива превышает лимит")

        md_paths: list[tuple[tuple[str, ...], str, bytes]] = []
        explicit_dirs: set[tuple[str, ...]] = set()

        for info in infos:
            raw_name = info.filename
            if raw_name.endswith("/"):
                sp = _safe_parts(raw_name.rstrip("/"))
                if sp:
                    explicit_dirs.add(sp)
                continue

            parts = _safe_parts(raw_name)
            if parts is None:
                continue
            if len(parts[-1]) < 4 or not parts[-1].lower().endswith(".md"):
                continue
            if info.file_size > MAX_SINGLE_FILE:
                raise ZipImportError(f"Файл слишком большой: {parts[-1]}")

            data = zf.read(info)
            if len(data) != info.file_size:
                raise ZipImportError("Несоответствие размера при чтении архива")

            title = PurePosixPath(parts[-1]).stem.strip() or parts[-1][:-3]
            if not title:
                raise ZipImportError("Пустое имя заметки")
            parent_dir = parts[:-1]
            md_paths.append((parent_dir, title, data))

        if not md_paths:
            raise ZipImportError("В архиве нет .md файлов")

        all_folder_keys: set[tuple[str, ...]] = set(explicit_dirs)
        for parent_dir, _title, _data in md_paths:
            all_folder_keys.update(_folder_keys_from_parent_dir(parent_dir))

        sorted_folders = sorted(all_folder_keys, key=lambda t: (len(t), t))
        path_to_id: dict[tuple[str, ...], uuid.UUID] = {}
        repo = ArticleRepository(db)

        for folder_parts in sorted_folders:
            if folder_parts in path_to_id:
                continue
            fk_parent = folder_parts[:-1] if len(folder_parts) >= 1 else ()
            if len(fk_parent) == 0:
                parent_uuid: uuid.UUID | None = None
            else:
                parent_uuid = path_to_id.get(fk_parent)
                if parent_uuid is None:
                    raise ZipImportError("Внутренняя ошибка: нет родителя для папки")

            name = folder_parts[-1]
            row = await repo.create(
                user_id=user_id,
                title=name[:500],
                content="",
                tag_pairs=[],
                chat_session_id=None,
                parent_id=parent_uuid,
                is_folder=True,
            )
            path_to_id[folder_parts] = row.id
            created += 1
            if parent_uuid is None:
                root_ids.append(row.id)

        md_paths.sort(key=lambda x: (x[0], x[1]))

        for parent_dir, title, data in md_paths:
            parent_uuid = path_to_id[parent_dir] if parent_dir else None
            text = data.decode("utf-8", errors="replace")
            row = await repo.create(
                user_id=user_id,
                title=title[:500],
                content=text,
                tag_pairs=[],
                chat_session_id=None,
                parent_id=parent_uuid,
                is_folder=False,
            )
            created += 1
            if parent_uuid is None:
                root_ids.append(row.id)

    return created, root_ids
