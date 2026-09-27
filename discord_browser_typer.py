"""Minimized-browser Discord typer — zero shared mouse/keys/focus.

Drives Discord WEB (not the desktop app) with Playwright DOM events:
locator.focus (in-page only) + pressSequentially + Enter. Nothing goes
through Windows input, so you can fully use your computer while it farms.

Channel: your OwO farm channel (set DISCORD_CHANNEL_URL — never commit it)
  Example: https://discord.com/channels/<guildId>/<channelId>

Usage:
  setx DISCORD_CHANNEL_URL "https://discord.com/channels/<guildId>/<channelId>"
  (reopen the terminal after setx, or export it per-session)
  python discord_browser_typer.py --setup    one-time manual login (~2 min)
  python discord_browser_typer.py --check    load channel, screenshot, no typing
  python discord_browser_typer.py --once     single wh/wb, minimized
  python discord_browser_typer.py            full loop (minimized)

NEVER run discord_typer.py (desktop) at the same time (double sends).
"""

import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _channel_url():
    url = os.environ.get("DISCORD_CHANNEL_URL", "").strip()
    if not url.startswith("https://discord.com/channels/"):
        raise SystemExit(
            "ERROR: set DISCORD_CHANNEL_URL first:\n"
            '  setx DISCORD_CHANNEL_URL "https://discord.com/channels/<guildId>/<channelId>"\n'
            "Then reopen your terminal (or export it for this session) and rerun."
        )
    return url


PROFILE_DIR = os.path.join(HERE, ".browser-profile")
STORAGE_FILE = os.path.join(HERE, "storage_state.json")
CHECK_SHOT = os.path.join(HERE, "channel_check.png")

MESSAGES = ["wh", "wb"]
MIN_DELAY = 11
MAX_DELAY = 19
BETWEEN_MESSAGES_DELAY = 0.6

TEXTBOX = 'div[role="textbox"]'


def _launch(pw, headed):
    ctx = pw.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=False,
        viewport={"width": 1280, "height": 800},
        args=["--disable-blink-features=AutomationControlled"],
    )
    return ctx


def _minimize_window():
    """Minimize our Chromium window (by process name, never the desktop
    app); page keeps running. Best effort."""
    try:
        import psutil
        import win32con
        import win32gui
        import win32process

        fg = win32gui.GetForegroundWindow()
        try:
            _, pid = win32process.GetWindowThreadProcessId(fg)
            exe = psutil.Process(pid).name().lower()
            if "chrome" in exe or "chromium" in exe or "msedge" in exe:
                win32gui.ShowWindow(fg, win32con.SW_MINIMIZE)
                return True
            print(f"minimize skipped (foreground is {exe}, not our browser)")
        except Exception:
            pass
    except Exception as e:
        print(f"minimize skipped ({e})")
    return False


def cmd_setup():
    from playwright.sync_api import sync_playwright

    print("=== ONE-TIME LOGIN ===")
    print("A Chromium window will open on Discord. Log in manually")
    print("(solve captcha/2FA if asked), land anywhere, then come back")
    print("here and press Enter. Session saves to storage_state.json")
    print("(gitignored — never share it, it's your login).")
    with sync_playwright() as pw:
        ctx = _launch(pw, headed=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://discord.com/login")
        input("Press Enter HERE after you are logged in... ")
        ctx.storage_state(path=STORAGE_FILE)
        print(f"Saved {STORAGE_FILE}. Login done — close the browser.")
        ctx.close()


def _open_channel(ctx):
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(_channel_url(), wait_until="domcontentloaded")
    page.wait_for_selector(TEXTBOX, timeout=60000)
    time.sleep(2.0)  # let Slate hydrate
    print(f"Channel loaded: {page.title()[:80]}")
    return page


def cmd_check():
    from playwright.sync_api import sync_playwright

    if not os.path.exists(STORAGE_FILE):
        print("No storage_state.json — run --setup first.")
        sys.exit(1)
    with sync_playwright() as pw:
        ctx = _launch(pw, headed=True)
        page = _open_channel(ctx)
        box = page.locator(TEXTBOX).first
        print(f"textbox visible={box.is_visible()} enabled={box.is_enabled()}")
        page.screenshot(path=CHECK_SHOT)
        print(f"Screenshot: {CHECK_SHOT} — confirm it's the OwO channel.")
        ctx.close()


def _send(page, msg):
    box = page.locator(TEXTBOX).first
    box.scroll_into_view_if_needed()
    box.click()  # DOM click, no system mouse involved
    box.press_sequentially(msg, delay=60)
    time.sleep(0.4)
    box.press("Enter")
    print(f"Sent: {msg}", flush=True)


def _run_loop(once):
    from playwright.sync_api import sync_playwright

    if not os.path.exists(STORAGE_FILE):
        print("No storage_state.json — run --setup first.")
        sys.exit(1)
    print("NEVER run discord_typer.py at the same time (double sends).")
    with sync_playwright() as pw:
        ctx = _launch(pw, headed=True)
        page = _open_channel(ctx)
        _minimize_window()
        print("Minimized. Fully use your computer — sends stay on schedule.")
        if once:
            for m in MESSAGES:
                _send(page, m)
                time.sleep(BETWEEN_MESSAGES_DELAY)
            ctx.close()
            return
        print("Running. Press Ctrl+C to stop.")
        try:
            while True:
                for m in MESSAGES:
                    _send(page, m)
                    time.sleep(BETWEEN_MESSAGES_DELAY)
                delay = random.uniform(MIN_DELAY, MAX_DELAY)
                print(f"Waiting {delay:.1f}s... (you're fully free)", flush=True)
                time.sleep(delay)
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            ctx.close()


def main():
    ap = argparse.ArgumentParser(description="Minimized-browser Discord typer.")
    ap.add_argument("--setup", action="store_true", help="one-time manual login")
    ap.add_argument("--check", action="store_true", help="load channel + screenshot, no typing")
    ap.add_argument("--once", action="store_true", help="single wh/wb, minimized")
    args = ap.parse_args()
    if args.setup:
        cmd_setup()
    elif args.check:
        cmd_check()
    else:
        _run_loop(once=args.once)


if __name__ == "__main__":
    main()
