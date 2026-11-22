"""Sends finished clips to your Telegram."""
import os
from pathlib import Path

import requests

from .log import log

API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _chat() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def send_message(text: str) -> bool:
    if not (_token() and _chat()):
        log.warning("Telegram not set up (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing in .env)")
        return False
    r = requests.post(API.format(token=_token(), method="sendMessage"),
                      data={"chat_id": _chat(), "text": text[:4000]}, timeout=60)
    if not r.ok:
        log.error("Telegram message failed: %s", r.text[:300])
    return r.ok


def send_video(path: Path, caption: str) -> bool:
    if not (_token() and _chat()):
        log.warning("Telegram not set up, clip saved only on the server: %s", path.name)
        return False
    with path.open("rb") as f:
        r = requests.post(
            API.format(token=_token(), method="sendVideo"),
            data={"chat_id": _chat(), "caption": caption[:1024], "supports_streaming": "true"},
            files={"video": (path.name, f, "video/mp4")},
            timeout=600,
        )
    if not r.ok:
        log.error("Telegram upload failed: %s", r.text[:300])
    return r.ok


def find_chat_ids() -> list:
    if not _token():
        raise SystemExit("Put TELEGRAM_BOT_TOKEN in .env first.")
    r = requests.get(API.format(token=_token(), method="getUpdates"), timeout=60)
    r.raise_for_status()
    chats = {}
    for upd in r.json().get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            chats[chat["id"]] = chat.get("first_name") or chat.get("title") or ""
    return list(chats.items())
