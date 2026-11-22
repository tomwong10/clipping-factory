"""Watches channels and records them in chunks while they are live."""
import json
import subprocess
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .config import INCOMING, Channel, Settings
from .log import log


def _streamlink() -> list:
    from shutil import which
    exe = which("streamlink")
    if exe:
        return [exe]
    venv = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "streamlink"
    return [str(venv)]


@lru_cache(maxsize=1)
def _duration_flag() -> str:
    try:
        out = subprocess.run(_streamlink() + ["--help"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        out = ""
    return "--stream-segmented-duration" if "--stream-segmented-duration" in out else "--hls-duration"


def is_live(url: str) -> bool:
    try:
        res = subprocess.run(_streamlink() + ["--json", url], capture_output=True, text=True, timeout=90)
        data = json.loads(res.stdout or "{}")
    except Exception as e:
        log.warning("Live check failed for %s: %s", url, e)
        return False
    return bool(data.get("streams")) and "error" not in data


def record_chunk(channel: Channel, settings: Settings) -> Path | None:
    """Records one chunk. Returns the finished file, or None if nothing useful was recorded."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    final = INCOMING / f"{channel.name}__{stamp}.ts"
    part = final.with_suffix(".part")
    secs = int(settings.chunk_minutes * 60)
    duration = f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
    cmd = _streamlink() + [
        "--retry-open", "3",
        "--force",
        _duration_flag(), duration,
        "-o", str(part),
    ]
    if "twitch.tv" in channel.url:
        cmd.append("--twitch-disable-ads")
    cmd += [channel.url, "best"]
    log.info("[%s] Recording chunk (%s min)", channel.name, settings.chunk_minutes)
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=secs + 600)
    except subprocess.TimeoutExpired:
        log.warning("[%s] Recording overran, using what we have", channel.name)
    if part.exists() and part.stat().st_size > 5_000_000:
        part.rename(final)
        log.info("[%s] Chunk saved: %s (%.0f MB)", channel.name, final.name, final.stat().st_size / 1e6)
        return final
    part.unlink(missing_ok=True)
    return None


def watch_channel(channel: Channel, settings: Settings, queue, stop: threading.Event) -> None:
    log.info("[%s] Watching %s", channel.name, channel.url)
    was_live = False
    while not stop.is_set():
        if is_live(channel.url):
            if not was_live:
                log.info("[%s] is LIVE", channel.name)
                was_live = True
            chunk = record_chunk(channel, settings)
            if chunk:
                queue.put(chunk)
            else:
                time.sleep(30)
            continue
        if was_live:
            log.info("[%s] went offline", channel.name)
            was_live = False
        stop.wait(settings.check_every_seconds)
