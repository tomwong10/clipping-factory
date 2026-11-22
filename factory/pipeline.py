"""Turns a recording into finished clips: transcribe, pick, edit, send."""
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import telegram
from .config import READY, WORK, Settings
from .editor import build_ass, make_clip
from .log import log
from .picker import pick_moments
from .transcribe import transcribe


def probe_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def split(path: Path, minutes: int) -> list:
    """Splits a long file into chunks without re-encoding."""
    out_dir = WORK / f"{path.stem}_parts"
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-f", "segment",
         "-segment_time", str(minutes * 60), "-reset_timestamps", "1",
         str(out_dir / "part%03d.ts")],
        check=True,
    )
    return sorted(out_dir.glob("part*.ts"))


def _caption(m: dict, channel) -> str:
    tags = []
    for t in list(m.get("hashtags") or []) + list(channel.hashtags):
        t = t if str(t).startswith("#") else f"#{t}"
        if t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    title = m.get("title") or f"{channel.name} moment"
    body = m.get("caption") or ""
    return "\n\n".join(x for x in (title, body, " ".join(tags[:8])) if x)


def process_chunk(video: Path, channel, settings: Settings) -> list:
    duration = probe_duration(video)
    if duration < 30:
        log.info("Skipping %s (too short)", video.name)
        return []
    segments = transcribe(video, settings.whisper_model, settings.language)
    if not segments:
        log.info("No speech found in %s", video.name)
        return []
    work = WORK / video.stem
    work.mkdir(parents=True, exist_ok=True)
    (work / "transcript.json").write_text(json.dumps(segments))

    moments = pick_moments(segments, channel, settings, duration)
    words = [w for s in segments for w in s["words"]]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    made = []
    for i, m in enumerate(moments, 1):
        name = f"{channel.name}_{stamp}_{i:02d}"
        ass = work / f"{name}.ass"
        out = READY / f"{name}.mp4"
        build_ass(words, m["start"], m["end"], ass, channel.credit)
        if not make_clip(video, m["start"], m["end"], ass, out, settings.layout):
            continue
        caption = _caption(m, channel)
        (READY / f"{name}.txt").write_text(caption + "\n")
        log.info("[%s] Clip ready: %s (%.0fs)", channel.name, out.name, m["end"] - m["start"])
        if settings.send_to_telegram:
            telegram.send_video(out, caption)
        made.append(out)
    shutil.rmtree(work, ignore_errors=True)
    return made


def process_file(path: Path, channel, settings: Settings) -> list:
    log.info("[%s] Processing %s", channel.name, path.name)
    made = []
    try:
        duration = probe_duration(path)
        if duration > settings.chunk_minutes * 60 * 1.25:
            parts = split(path, settings.chunk_minutes)
            for p in parts:
                made += process_chunk(p, channel, settings)
                p.unlink(missing_ok=True)
            shutil.rmtree(parts[0].parent, ignore_errors=True) if parts else None
        else:
            made = process_chunk(path, channel, settings)
    except Exception:
        log.exception("[%s] Failed to process %s", channel.name, path.name)
        failed = path.with_suffix(path.suffix + ".failed")
        if path.exists():
            path.rename(failed)
        return made
    if not settings.keep_raw:
        path.unlink(missing_ok=True)
    log.info("[%s] Done with %s: %d clips", channel.name, path.name, len(made))
    return made


def cleanup_ready(days: int) -> None:
    cutoff = time.time() - days * 86400
    for f in READY.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
