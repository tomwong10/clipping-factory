# Clip Factory

Records live streams overnight, finds the best moments, cuts them to vertical 9:16 with bold animated captions, and sends each clip with a title, caption and hashtags to your Telegram.

**How it works:** Streamlink records streams in 45-minute chunks. Whisper turns the speech into text. Claude Code (your Pro plan) picks the viral moments. FFmpeg edits the clips, and Telegram delivers them.

## Setup on the server (Ubuntu 24.04)

```bash
git clone https://github.com/tomwong10/clipping-factory.git
cd clipping-factory
chmod +x install.sh
./install.sh
```

The install script prints the next steps when it finishes. In short:

1. `source ~/.bashrc && claude`: log in with your Claude Pro account, then type `/exit`
2. `nano .env`: paste your Telegram bot token
3. `.venv/bin/python -m factory chat-id`: copy your chat ID into `.env`
4. `.venv/bin/python -m factory check`: every line should say OK
5. Test on a past stream: `.venv/bin/python -m factory vod "LINK" --channel lacy --to 00:30:00`
6. Go live: `sudo systemctl enable --now clip-factory`

## Everyday commands

| What | Command |
| --- | --- |
| Is it running? | `systemctl status clip-factory` |
| Watch the log live | `tail -f logs/factory.log` (Ctrl+C to stop watching) |
| Restart after changing settings | `sudo systemctl restart clip-factory` |
| Stop it | `sudo systemctl stop clip-factory` |
| Clip a specific past stream (campaigns) | `.venv/bin/python -m factory vod "LINK" --channel kaicenat --from 01:00:00 --to 03:00:00` |

## Settings

Edit `config.toml` (`nano config.toml`) to change the channels, campaign rules, clip length, clips per hour or layout. Then restart the service.

## Notes

- Only clip streamers whose campaign or program allows it, and follow each campaign's brief.
- Post the clips yourself. Auto-posting gets accounts flagged.
- `.env` holds your Telegram token and is never uploaded to GitHub.
