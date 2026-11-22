#!/usr/bin/env bash
# One-command setup for Ubuntu/Debian servers. Run from inside the clip-factory folder: ./install.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Installing system tools (ffmpeg, python, git)..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg python3 python3-venv python3-pip git curl fontconfig tmux

echo "==> Installing Python packages (streamlink, yt-dlp, faster-whisper)..."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> Downloading caption font..."
mkdir -p assets/fonts
curl -fsSL -o assets/fonts/Anton-Regular.ttf \
  https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf \
  || echo "   (font download failed, captions will use a default font)"

[ -f config.toml ] || cp config.example.toml config.toml
[ -f .env ] || cp .env.example .env

if ! command -v claude >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/claude" ]; then
  echo "==> Installing Claude Code..."
  curl -fsSL https://claude.ai/install.sh | bash
fi
grep -q '.local/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"

echo "==> Setting up the background service..."
sed -e "s|__USER__|$USER|g" -e "s|__DIR__|$PWD|g" -e "s|__HOME__|$HOME|g" \
  deploy/clip-factory.service | sudo tee /etc/systemd/system/clip-factory.service >/dev/null
sudo systemctl daemon-reload

cat <<'EOF'

==========================================================
 Install finished. Next steps:
  1. source ~/.bashrc && claude        (log in with your Pro account, then type /exit)
  2. nano .env                         (paste your Telegram bot token, Ctrl+O, Enter, Ctrl+X)
  3. .venv/bin/python -m factory chat-id   (copy the number into .env as TELEGRAM_CHAT_ID)
  4. .venv/bin/python -m factory check
  5. Test:  .venv/bin/python -m factory vod "VOD_LINK" --channel lacy --to 00:30:00
  6. Go live: sudo systemctl enable --now clip-factory
==========================================================
EOF
