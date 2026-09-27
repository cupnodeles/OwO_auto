# Discord Auto-Typer (OwO Farm)

Sends `wh` / `wb` to your OwO farm channel on a schedule while you use your computer.
Two senders exist — use **one at a time, never both**.

## UI only (no terminal commands needed after install)

```powershell
git clone https://github.com/cupnodeles/OwO_auto.git
cd OwO_auto
pip install -r requirements.txt
python -m playwright install chromium
python owo_ui.py
```

In the popup: fill **Server** + **Channel** → `Save` → `Setup` (one-time login)
→ `Check` → `Once` → `Start`. That's the whole flow — everything else below
is optional terminal detail.

## Prerequisites

- Windows 10/11 with Python 3.10+ ([python.org](https://www.python.org/downloads/),
  tick **Add python.exe to PATH** during install). Check with:
```powershell
python --version
```
- Git (to clone the repo).

## Install

```powershell
git clone https://github.com/cupnodeles/OwO_auto.git
cd OwO_auto
pip install -r requirements.txt
python -m playwright install chromium   # browser sender only (~150 MB)
```

What each package is for: `pyautogui` (desktop click/type), `pywin32`
(window focus APIs), `pywinauto` + `uiautomation` (message-box detection),
`psutil` (process checks), `playwright` + its Chromium download (browser sender).

Set your channel (browser sender) — find it via right-click channel → Copy Link:
```powershell
setx DISCORD_CHANNEL_URL "https://discord.com/channels/<guildId>/<channelId>"
```
Reopen the terminal after `setx`, or export it for one session:
```powershell
$env:DISCORD_CHANNEL_URL = "https://discord.com/channels/<guildId>/<channelId>"
```

## Files

| File | What it does |
|---|---|
| `discord_typer.py` | Desktop-app sender (focus-borrow, human-speed typing) |
| `discord_detector.py` | Finds the Discord window + message box, focus/gate helpers |
| `discord_browser_typer.py` | Minimized-browser sender (zero shared mouse/keys, recommended for full PC use) |
| `owo_ui.py` | 🐄 OwO-styled popup: server/channel/commands config + Start/Stop (no terminal needed) |

## Control panel (easiest)

```powershell
cd OwO_auto
python owo_ui.py
```

Fill **Server** (guild ID or `discord.gg/xxx` invite), **Channel** (ID),
edit **Commands** (default `wh`, `wb` — Add/Remove/Up/Down), tune delays,
then `Save` → `Setup` (one-time login) → `Check` → `Once` → `Start`.
Logs stream inside the popup; `Stop` ends the run. Settings save to
`config.json` (local, gitignored — IDs never touch git).

## Path A — Browser sender (recommended)

Fully background: minimized Chromium, DOM-level input. Your mouse, keyboard,
and screen are 100% yours while it farms.

```powershell
cd OwO_auto

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
(Reads `DISCORD_CHANNEL_URL` set in Install above.)

## Path B — Desktop-app sender

Types into the Discord desktop app like a human (char-by-char + single Enter).
Discord pops to front briefly per send (~3s), then returns you to your app for
the 11–19s gaps. Don't type in that Discord channel yourself while it runs.

```powershell
cd OwO_auto
# (deps already installed via pip install -r requirements.txt above)

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
