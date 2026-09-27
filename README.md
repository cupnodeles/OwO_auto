# Discord Auto-Typer (OwO Farm)

Sends `wh` / `wb` to your OwO farm channel on a schedule while you use your computer.
Two senders exist — use **one at a time, never both**.

## Files

| File | What it does |
|---|---|
| `discord_typer.py` | Desktop-app sender (focus-borrow, human-speed typing) |
| `discord_detector.py` | Finds the Discord window + message box, focus/gate helpers |
| `discord_browser_typer.py` | Minimized-browser sender (zero shared mouse/keys, recommended for full PC use) |

## Path A — Browser sender (recommended)

Fully background: minimized Chromium, DOM-level input. Your mouse, keyboard,
and screen are 100% yours while it farms.

```powershell
cd C:\Users\DELL\Downloads\DC
pip install playwright
python -m playwright install chromium

# 1. One-time manual login (~2 min). Log in when the window opens,
#    then press Enter in the terminal. Saves storage_state.json.
python discord_browser_typer.py --setup

# 2. Verify it opens the right channel (screenshot, no typing).
python discord_browser_typer.py --check
#    Open channel_check.png and confirm it's the OwO farm channel.

# 3. Single minimized send.
python discord_browser_typer.py --once

# 4. Full loop: wh -> 0.6s -> wb -> random 11-19s.
python discord_browser_typer.py
```

Target channel: set `DISCORD_CHANNEL_URL` (right-click the channel → Copy Link):
```
setx DISCORD_CHANNEL_URL "https://discord.com/channels/<guildId>/<channelId>"
```
Reopen the terminal after `setx`, then run the commands above.

## Path B — Desktop-app sender

Types into the Discord desktop app like a human (char-by-char + single Enter).
Discord pops to front briefly per send (~3s), then returns you to your app for
the 11–19s gaps. Don't type in that Discord channel yourself while it runs.

```powershell
cd C:\Users\DELL\Downloads\DC
pip install pyautogui pywinauto pywin32 uiautomation psutil

python discord_typer.py --once --dry-run   # detect only, no typing
python discord_typer.py --hover-test       # move mouse to box, screenshot it
python discord_typer.py --focus-test       # focus box via API, no typing
python discord_typer.py --notepad-test     # OS-level key check in Notepad
python discord_typer.py --once --keep-focus  # single live wh/wb
python discord_typer.py                    # full loop
```

Safety rails built in: landing guard (aborts on miss, zero blind keys),
first-char gate (aborts if Slate doesn't recognize input), skip-while-you-type,
composer reset instead of manual channel-switching. Logs to watch for:
`landing verified` + `gate passed` = healthy send.

## Safety (read this — main account)

- OwO + Discord forbid automation. Short sessions only; **stop instantly on any
  captcha, warning, or DM from OwO**. 24/7 farming on a main gets banned.
- `storage_state.json` is your login session — never share or commit it
  (already in `.gitignore`, with `.browser-profile/` and `channel_check.png`).
- A webhook URL was previously posted publicly — regenerate it in
  Discord Settings → Integrations → Webhooks. The local `.env` is deleted.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Text sits unsent, faded placeholder overlaps | Slate desync — switch channel away and back once to remount, then rerun |
| `Click missed editable` every cycle | Re-run `--hover-test`, screenshot, retune offsets in `find_message_box` |
| `You're typing in Discord — skipping` loop | Stop typing in that channel or stop the script; it yields to you |
| Browser asks login again | Session expired — rerun `--setup` |
| Minimized browser stops sending | Chromium throttled it — keep window behind others instead of minimized |
