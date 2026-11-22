"""Loads config.toml and .env."""
import os
import re
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INCOMING = DATA / "incoming"
WORK = DATA / "work"
READY = ROOT / "output" / "ready"
LOGS = ROOT / "logs"
FONTS = ROOT / "assets" / "fonts"

for _d in (INCOMING, WORK, READY, LOGS, FONTS):
    _d.mkdir(parents=True, exist_ok=True)


@dataclass
class Channel:
    name: str
    url: str = ""
    credit: str = ""
    hashtags: list = field(default_factory=list)
    campaign_notes: str = ""
    enabled: bool = True


@dataclass
class Settings:
    whisper_model: str = "small"
    language: str = "en"
    chunk_minutes: int = 45
    clips_per_hour: int = 4
    min_clip_seconds: int = 15
    max_clip_seconds: int = 60
    layout: str = "blur"
    check_every_seconds: int = 120
    keep_raw: bool = False
    keep_ready_days: int = 3
    send_to_telegram: bool = True
    channels: list = field(default_factory=list)

    def channel(self, name: str) -> Channel:
        for c in self.channels:
            if c.name == name:
                return c
        return Channel(name=name, credit=f"@{name}")


def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def _pick(cls, data: dict) -> dict:
    allowed = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in allowed}


def load() -> Settings:
    load_env()
    path = ROOT / "config.toml"
    if not path.exists():
        raise SystemExit("config.toml is missing. Run: cp config.example.toml config.toml")
    data = tomllib.loads(path.read_text())
    settings = Settings(**_pick(Settings, data.get("general", {})))
    for raw in data.get("channels", []):
        ch = Channel(**_pick(Channel, raw))
        if not re.fullmatch(r"[A-Za-z0-9-]+", ch.name):
            raise SystemExit(f"Channel name '{ch.name}' can only use letters, numbers and dashes.")
        settings.channels.append(ch)
    return settings
