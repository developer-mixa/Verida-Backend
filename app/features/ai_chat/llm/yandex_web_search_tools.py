"""Один инструмент `web_search` для Yandex Responses API (дубликаты type web_search дают 400)."""

from __future__ import annotations

import os
from typing import Any

# Опционально: ограничить единственный web_search только этими доменами (см. .env.example).
_SCIENCE_ALLOWED_DOMAINS: list[str] = [
    "pubmed.ncbi.nlm.nih.gov",
    "europepmc.org",
    "pmc.ncbi.nlm.nih.gov",
    "www.ncbi.nlm.nih.gov",
    "www.nature.com",
    "www.science.org",
    "www.sciencemag.org",
    "www.cell.com",
    "arxiv.org",
    "export.arxiv.org",
    "www.biorxiv.org",
    "www.medrxiv.org",
    "doi.org",
    "link.springer.com",
    "onlinelibrary.wiley.com",
    "academic.oup.com",
    "journals.plos.org",
    "www.frontiersin.org",
    "www.mdpi.com",
    "www.tandfonline.com",
    "www.embopress.org",
    "journals.asm.org",
    "peerj.com",
    "elifesciences.org",
    "www.semanticscholar.org",
    "api.semanticscholar.org",
    "cyberleninka.ru",
    "elibrary.ru",
    "www.pnas.org",
    "journals.aps.org",
]


def yandex_responses_web_search_tools() -> list[dict[str, Any]]:
    """
    Ровно один объект `{"type": "web_search", ...}` — API Yandex не принимает два web_search в одном запросе.

    По умолчанию поиск по **всему интернету** (`search_context_size: high`), чтобы модель могла
    несколькими вызовами одного инструмента сначала искать по научным формулировкам, затем расширять запрос.

    Если задано `YANDEX_WEB_SEARCH_ONLY_SCIENCE_DOMAINS=1` — добавляется `filters.allowed_domains` (только научные сайты).

    Опционально `YANDEX_WEB_SEARCH_REGION` — код региона (например, 213 для Москвы).
    """
    region = (os.getenv("YANDEX_WEB_SEARCH_REGION") or "").strip()
    science_only = (os.getenv("YANDEX_WEB_SEARCH_ONLY_SCIENCE_DOMAINS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    filters: dict[str, Any] = {}
    if region:
        filters["user_location"] = {"region": region}
    if science_only:
        filters["allowed_domains"] = list(_SCIENCE_ALLOWED_DOMAINS)

    tool: dict[str, Any] = {
        "type": "web_search",
        "search_context_size": "medium",
    }
    if filters:
        tool["filters"] = filters

    return [tool]
