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


def _expected_ids():
    """(guild_id, channel_id) parsed from DISCORD_CHANNEL_URL."""
    parts = _channel_url().rstrip("/").split("/")
    return (parts[-2], parts[-1])


def _describe_boxes(page):
    """List every textbox candidate: name, box, in-thread-panel guess."""
    items = []
    loc = page.locator(TEXTBOX)
    try:
        n = loc.count()
    except Exception:
        return items
    for i in range(n):
        el = loc.nth(i)
        try:
            name = el.get_attribute("aria-label") or ""
        except Exception:
            name = ""
        try:
            bb = el.bounding_box()
        except Exception:
            bb = None
        try:
            in_aside = el.evaluate(
                "el => !!el.closest('aside,[role=complementary],[aria-label*=Thread i]')"
            )
        except Exception:
            in_aside = None
        items.append({"index": i, "name": name, "box": bb, "in_thread": in_aside})
    return items


def _main_box(page):
    """Pick the MAIN channel composer, never a thread panel's.

    Rule: visible textbox whose accessible name starts with 'Message',
    widest box in the bottom 45% of the viewport (thread panel boxes
    are narrow, right-side). Raises SystemExit-detail via return None.
    """
    cands = [c for c in _describe_boxes(page) if (c["name"] or "").lower().startswith("message")]
    cands = [c for c in cands if c["box"] and c["box"]["width"] > 200]
    if not cands:
        return None, "no Message* textbox found"
    try:
        vh = page.viewport_size["height"]
    except Exception:
        vh = 800
    low = [c for c in cands if c["box"]["y"] > vh * 0.55]
    pool = low or cands
    # Prefer non-thread-panel candidates; fall back to widest overall.
    main = [c for c in pool if c["in_thread"] is False]
    pool = main or pool
    best = max(pool, key=lambda c: c["box"]["width"])
    return page.locator(TEXTBOX).nth(best["index"]), None


def _verify_channel(page):
    """Confirm we are on the expected channel. Returns (ok, detail)."""
    _, channel_id = _expected_ids()
    url = page.url
    if channel_id not in url:
        return False, f"URL drifted: {url[:100]}"
    want = os.environ.get("DISCORD_CHANNEL_NAME", "").strip().lower()
    header = ""
    for sel in ["main h1", "main h2", 'header h1', '[data-list-item-id]']:
        try:
            t = page.locator(sel).first.inner_text(timeout=2000).strip()
            if t:
                header = t
                break
        except Exception:
            continue
    if want and want not in header.lower():
        return False, f"header {header!r} lacks {want!r}"
    return True, f"url ok + header {header[:60]!r}"


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
        for c in _describe_boxes(page):
            print(f"box#{c['index']} name={c['name'][:70]!r} box={c['box']} in_thread={c['in_thread']}")
        el, err = _main_box(page)
        if el is None:
            print(f"MAIN SELECT: FAILED ({err})")
        else:
            print("MAIN SELECT: ok (widest bottom Message* box, thread panel excluded)")
        ok, detail = _verify_channel(page)
        print(f"CHANNEL VERIFY: {'ok' if ok else 'MISMATCH'} ({detail})")
        page.screenshot(path=CHECK_SHOT)
        print(f"Screenshot: {CHECK_SHOT} — confirm it's the OwO channel.")
        ctx.close()


def _send(page, msg):
    ok, detail = _verify_channel(page)
    if not ok:
        print(f"SKIP {msg}: {detail} (no keys sent)")
        return False
    el, err = _main_box(page)
    if el is None:
        print(f"SKIP {msg}: {err} (no keys sent)")
        return False
    box = el
    box.scroll_into_view_if_needed()
    box.click()  # DOM click, no system mouse involved
    box.press_sequentially(msg, delay=60)
    time.sleep(0.4)
    box.press("Enter")
    print(f"Sent: {msg}", flush=True)
    return True


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
