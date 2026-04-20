from __future__ import annotations

from os import getenv

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

folder_id = getenv("YANDEX_GPT_FOLDER_ID") or ""
api_key = getenv("YANDEX_GPT_API_KEY") or ""
base_url = getenv("YANDEX_GPT_BASE_URL")

model = getenv("YANDEX_GPT_MODEL")

client = OpenAI(
    base_url=base_url,
    api_key=api_key,
    project=folder_id,
)
