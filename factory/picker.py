"""Finds the best moments in a transcript. Uses Claude Code (your Pro plan) with a simple backup."""
import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import Channel, Settings
from .log import log

PROMPT = """You are an elite short-form editor who makes viral TikTok, YouTube Shorts and Reels clips from livestreams.
The text you receive is a transcript of a livestream by {name}. Each line is [start_seconds-end_seconds] what was said.

Campaign rules to follow: {notes}

Pick up to {count} moments that work as standalone viral clips: big reactions, funny moments, hype, shocking or
hot-take lines, chaos, wholesome moments. Rules:
- Each clip is {min_s} to {max_s} seconds long.
- Start right before the hook (no slow build-up) and end just after the payoff.
- The clip must make sense without context.
- Skip ads, sponsor reads, dead air, and anything that breaks TikTok rules (slurs, sexual content, gambling promotion).
- Clips must not overlap.

For each clip write:
- title: punchy and curiosity-driven, max 60 characters, never misleading
- caption: 1 short line that makes people watch to the end, emoji allowed
- hashtags: 3 to 5 relevant hashtags

Reply with ONLY a JSON array and nothing else:
[{{"start": 123.4, "end": 160.2, "score": 9, "title": "...", "caption": "...", "hashtags": ["#..."]}}]
Score is 1-10 for how viral it will be."""

HYPE = re.compile(
    r"\b(no way|oh my god|omg|what the|bro|bruh|let'?s go|yo+|crazy|insane|stop|wait|hell nah|nah)\b|!",
    re.I,
)


def _claude_bin() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "claude"
    return str(local) if local.exists() else None


def _transcript_text(segments: list) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments if s["text"])


def _parse(text: str) -> list:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("no JSON array in reply")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("reply was not a list")
    return data


def ask_claude(segments: list, channel: Channel, settings: Settings, count: int) -> list:
    exe = _claude_bin()
    if not exe:
        raise RuntimeError("Claude Code is not installed or not on PATH")
    prompt = PROMPT.format(
        name=channel.name,
        notes=channel.campaign_notes or "none",
        count=count,
        min_s=settings.min_clip_seconds,
        max_s=settings.max_clip_seconds,
    )
    transcript = _transcript_text(segments)[:120_000]
    res = subprocess.run(
        [exe, "-p", prompt, "--output-format", "text"],
        input=transcript, capture_output=True, text=True, timeout=900,
    )
    if res.returncode != 0:
        raise RuntimeError(f"claude exited {res.returncode}: {res.stderr.strip()[:300]}")
    return _parse(res.stdout)


def fallback(segments: list, settings: Settings, count: int) -> list:
    """Backup when Claude is unavailable: scores windows by hype words and speech speed."""
    scored = []
    for i, s in enumerate(segments):
        window = [x for x in segments[i:i + 12] if x["start"] - s["start"] < settings.max_clip_seconds]
        text = " ".join(x["text"] for x in window)
        dur = max(1.0, window[-1]["end"] - s["start"])
        words = sum(len(x["text"].split()) for x in window)
        score = len(HYPE.findall(text)) * 2 + words / dur
        scored.append({
            "start": s["start"], "end": window[-1]["end"], "score": round(score, 2),
            "title": "", "caption": "", "hashtags": [],
        })
    scored.sort(key=lambda m: m["score"], reverse=True)
    return scored[: count * 3]


def _snap(m: dict, words: list, duration: float, settings: Settings) -> dict | None:
    try:
        start, end = float(m["start"]), float(m["end"])
    except (KeyError, TypeError, ValueError):
        return None
    start, end = max(0.0, start), min(duration, end)
    before = [w["start"] for w in words if w["start"] <= start + 0.05]
    after = [w["end"] for w in words if w["end"] >= end - 0.05]
    if before:
        start = max(0.0, before[-1] - 0.25)
    if after:
        end = min(duration, after[0] + 0.4)
    length = end - start
    if length > settings.max_clip_seconds:
        end = start + settings.max_clip_seconds
    elif length < settings.min_clip_seconds:
        end = min(duration, start + settings.min_clip_seconds)
    if end - start < 5:
        return None
    m = dict(m)
    m["start"], m["end"] = round(start, 2), round(end, 2)
    return m


def pick_moments(segments: list, channel: Channel, settings: Settings, duration: float) -> list:
    hours = max(duration / 3600, 0.25)
    count = max(1, round(settings.clips_per_hour * hours))
    try:
        raw = ask_claude(segments, channel, settings, count)
        log.info("[%s] Claude picked %d moments", channel.name, len(raw))
    except Exception as e:
        log.warning("[%s] Claude picking failed (%s), using backup picker", channel.name, e)
        raw = fallback(segments, settings, count)

    words = [w for s in segments for w in s["words"]]
    moments = []
    for m in sorted(raw, key=lambda x: float(x.get("score", 0) or 0), reverse=True):
        snapped = _snap(m, words, duration, settings)
        if not snapped:
            continue
        if any(snapped["start"] < o["end"] and o["start"] < snapped["end"] for o in moments):
            continue
        moments.append(snapped)
        if len(moments) >= count:
            break
    return sorted(moments, key=lambda m: m["start"])
