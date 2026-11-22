"""Commands:
  python -m factory check                  check everything is installed and set up
  python -m factory chat-id                find your Telegram chat ID
  python -m factory test-telegram          send a test message to Telegram
  python -m factory vod URL --channel NAME [--from 01:00:00 --to 02:00:00]
                                           clip a past stream (good for testing and campaigns)
  python -m factory process FILE --channel NAME
                                           clip a video file already on the server
  python -m factory watch                  run the factory: watch channels and clip them live
"""
import argparse
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config, telegram
from .log import log


def cmd_check(_args) -> None:
    ok = True

    def show(label, good, tip=""):
        nonlocal ok
        ok &= bool(good)
        print(f"  {'OK ' if good else 'NO '} {label}" + ("" if good else f"  -> {tip}"))

    print("Clip Factory check:")
    show("ffmpeg", shutil.which("ffmpeg"), "run ./install.sh")
    venv_bin = config.ROOT / ".venv" / "bin"
    show("streamlink", shutil.which("streamlink") or (venv_bin / "streamlink").exists(), "run ./install.sh")
    show("yt-dlp", shutil.which("yt-dlp") or (venv_bin / "yt-dlp").exists(), "run ./install.sh")
    try:
        import faster_whisper  # noqa: F401
        show("faster-whisper", True)
    except ImportError:
        show("faster-whisper", False, "run ./install.sh")
    claude = shutil.which("claude") or (Path.home() / ".local/bin/claude").exists()
    show("Claude Code", claude, "run: curl -fsSL https://claude.ai/install.sh | bash, then type claude to log in")
    show("caption font", (config.FONTS / "Anton-Regular.ttf").exists(), "optional, re-run ./install.sh")
    try:
        s = config.load()
        show(f"config.toml ({len(s.channels)} channels)", s.channels, "add [[channels]] to config.toml")
    except SystemExit as e:
        show("config.toml", False, str(e))
    show("Telegram token", os.environ.get("TELEGRAM_BOT_TOKEN"), "add it to .env")
    show("Telegram chat ID", os.environ.get("TELEGRAM_CHAT_ID"), "run: .venv/bin/python -m factory chat-id")
    print("\nAll good!" if ok else "\nFix the NO lines above, then run this again.")


def cmd_chat_id(_args) -> None:
    config.load_env()
    chats = telegram.find_chat_ids()
    if not chats:
        print("No messages found. Open your bot in Telegram, press Start, send it 'hi', then run this again.")
        return
    for cid, name in chats:
        print(f"Chat ID: {cid}   ({name})")
    print("\nPut it in .env as TELEGRAM_CHAT_ID=...")


def cmd_test_telegram(_args) -> None:
    config.load_env()
    print("Sent!" if telegram.send_message("Clip Factory is connected ✅") else "Failed, check the token and chat ID in .env")


def _ytdlp() -> str:
    return shutil.which("yt-dlp") or str(config.ROOT / ".venv" / "bin" / "yt-dlp")


def cmd_vod(args) -> None:
    from .pipeline import process_file
    settings = config.load()
    channel = settings.channel(args.channel)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_tmpl = str(config.INCOMING / f"vod-{channel.name}__{stamp}.%(ext)s")
    cmd = [_ytdlp(), "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
           "-o", out_tmpl, args.url]
    if args.start or args.end:
        cmd += ["--download-sections", f"*{args.start or '0'}-{args.end or 'inf'}"]
    log.info("Downloading %s", args.url)
    subprocess.run(cmd, check=True)
    files = sorted(config.INCOMING.glob(f"vod-{channel.name}__{stamp}.*"))
    if not files:
        raise SystemExit("Download failed, nothing saved.")
    made = process_file(files[0], channel, settings)
    print(f"\nMade {len(made)} clips in output/ready")


def cmd_process(args) -> None:
    from .pipeline import process_file
    settings = config.load()
    made = process_file(Path(args.file), settings.channel(args.channel), settings)
    print(f"\nMade {len(made)} clips in output/ready")


def cmd_watch(_args) -> None:
    from .pipeline import cleanup_ready, process_file
    from .recorder import watch_channel
    settings = config.load()
    channels = [c for c in settings.channels if c.enabled and c.url]
    if not channels:
        raise SystemExit("No channels in config.toml")
    jobs: queue.Queue = queue.Queue()
    stop = threading.Event()

    for leftover in sorted(config.INCOMING.glob("*.ts")):  # finish anything from before a restart
        jobs.put(leftover)
    for c in channels:
        threading.Thread(target=watch_channel, args=(c, settings, jobs, stop), daemon=True).start()

    log.info("Factory running with %d channels: %s", len(channels), ", ".join(c.name for c in channels))
    last_cleanup = 0.0
    try:
        while True:
            try:
                path = jobs.get(timeout=60)
            except queue.Empty:
                path = None
            if path is not None and Path(path).exists():
                name = Path(path).name.split("__")[0].removeprefix("vod-")
                process_file(Path(path), settings.channel(name), settings)
            if time.time() - last_cleanup > 3600:
                cleanup_ready(settings.keep_ready_days)
                last_cleanup = time.time()
    except KeyboardInterrupt:
        log.info("Stopping")
        stop.set()


def main() -> None:
    p = argparse.ArgumentParser(prog="factory", description="Clip Factory")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("chat-id").set_defaults(fn=cmd_chat_id)
    sub.add_parser("test-telegram").set_defaults(fn=cmd_test_telegram)
    v = sub.add_parser("vod")
    v.add_argument("url")
    v.add_argument("--channel", required=True)
    v.add_argument("--from", dest="start")
    v.add_argument("--to", dest="end")
    v.set_defaults(fn=cmd_vod)
    pr = sub.add_parser("process")
    pr.add_argument("file")
    pr.add_argument("--channel", required=True)
    pr.set_defaults(fn=cmd_process)
    sub.add_parser("watch").set_defaults(fn=cmd_watch)
    args = p.parse_args()
    args.fn(args)
