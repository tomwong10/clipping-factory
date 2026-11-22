"""Cuts clips to vertical 9:16 with bold word-by-word captions."""
import subprocess
from pathlib import Path

from .config import FONTS
from .log import log

FONT = "Anton"  # downloaded by install.sh; falls back to a default font if missing
YELLOW = "&H0000FFFF"  # ASS colours are &HAABBGGRR
WHITE = "&H00FFFFFF"

ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},104,{WHITE},{WHITE},&H00000000,&H99000000,-1,0,0,0,100,100,2,0,1,8,4,5,60,60,0,1
Style: Credit,{FONT},60,{WHITE},{WHITE},&H00000000,&H99000000,-1,0,0,0,100,100,1,0,1,5,2,8,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _t(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(word: str) -> str:
    return word.replace("{", "(").replace("}", ")").replace("\\", "").upper()


def _chunks(words: list, size: int = 3, gap: float = 0.6) -> list:
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= size or w["start"] - cur[-1]["end"] > gap):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def build_ass(words: list, start: float, end: float, path: Path, credit: str = "", disclosure: str = "") -> None:
    clip_words = [w for w in words if w["end"] > start and w["start"] < end]
    lines = [ASS_HEADER]
    cap_y = 1300
    for group in _chunks(clip_words):
        g_end = group[-1]["end"] - start
        for i, w in enumerate(group):
            t0 = max(w["start"], start) - start
            t1 = (group[i + 1]["start"] - start) if i + 1 < len(group) else g_end + 0.15
            if t1 <= t0:
                continue
            parts = []
            for j, other in enumerate(group):
                txt = _clean(other["word"])
                if j == i:
                    parts.append(f"{{\\c{YELLOW}\\fscx118\\fscy118}}{txt}{{\\c{WHITE}\\fscx100\\fscy100}}")
                else:
                    parts.append(txt)
            pop = "{\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}" if i == 0 else ""
            lines.append(
                f"Dialogue: 0,{_t(t0)},{_t(t1)},Cap,,0,0,0,,{{\\an5\\pos(540,{cap_y})}}{pop}{' '.join(parts)}\n"
            )
    if credit:
        lines.append(f"Dialogue: 1,{_t(0)},{_t(end - start)},Credit,,0,0,0,,{{\\an8\\pos(540,150)}}{_clean(credit)}\n")
    if disclosure:
        lines.append(f"Dialogue: 1,{_t(0)},{_t(min(3.0, end - start))},Credit,,0,0,0,,{{\\an8\\pos(540,230)\\fs44}}{_clean(disclosure)}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _filter(layout: str, ass_name: str) -> str:
    subs = f"ass={ass_name}:fontsdir={FONTS}"
    if layout == "crop":
        return f"[0:v]scale=-2:1920,crop=1080:1920,{subs}[v]"
    return (
        "[0:v]split=2[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=25:2,eq=brightness=-0.08[bg];"
        "[b]scale=1080:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2-200,{subs}[v]"
    )


def make_clip(src: Path, start: float, end: float, ass_path: Path, out: Path, layout: str = "blur") -> bool:
    def run(crf: int, maxrate: str) -> bool:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start:.2f}", "-i", str(src.resolve()), "-t", f"{end - start:.2f}",
            "-filter_complex", _filter(layout, ass_path.name),
            "-map", "[v]", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-maxrate", maxrate, "-bufsize", "12M", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            str(out.resolve()),
        ]
        res = subprocess.run(cmd, cwd=ass_path.parent, capture_output=True, text=True)
        if res.returncode != 0:
            log.error("ffmpeg failed: %s", res.stderr.strip()[-500:])
            return False
        return True

    if not run(21, "6M"):
        return False
    if out.stat().st_size > 48_000_000:  # Telegram bots can send up to 50 MB
        log.info("Clip too big for Telegram, compressing")
        return run(27, "4M")
    return True
