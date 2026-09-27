import argparse
import ctypes
import random
import time

import pyautogui
import win32con
import win32gui

import discord_detector

# Safety: move mouse to top-left corner to abort
pyautogui.FAILSAFE = True

MESSAGES = ["wh", "wb"]
MIN_DELAY = 11
MAX_DELAY = 19
STARTUP_DELAY = 5
BETWEEN_MESSAGES_DELAY = 0.6
TYPE_INTERVAL = 0.06
FOCUS_SETTLE = 0.35
CLICK_SETTLE = 0.25
WRITE_SETTLE = 0.4
ENTER_SETTLE = 0.7
USER_ACTIVE_MS = 3000

_jam_count = 0
_last_auto_tick = 0


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _now_tick():
    try:
        return ctypes.windll.kernel32.GetTickCount()
    except Exception:
        return int(time.time() * 1000)


def _mark_auto():
    global _last_auto_tick
    _last_auto_tick = _now_tick()


def _user_idle_ms():
    try:
        li = _LastInput(ctypes.sizeof(_LastInput), 0)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
        return ctypes.windll.kernel32.GetTickCount() - li.dwTime
    except Exception:
        return 10**9


def _ensure_foreground(hwnd, tries=3):
    for _ in range(tries):
        try:
            if win32gui.GetForegroundWindow() == hwnd:
                return True
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.3)
    try:
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        return False


def _type_text(text):
    """Human-speed typing Slate accepts: sequential keydown/keypress/keyup
    with per-char rhythm (original working behavior). No bursts."""
    for ch in text:
        pyautogui.write(ch, interval=TYPE_INTERVAL)
        time.sleep(random.uniform(0.02, 0.05))


def _press_enter():
    # Single human Enter (original working behavior). No double-tap,
    # no Esc, no clipboard — extras poisoned Slate.
    time.sleep(0.2)
    pyautogui.press("enter")


def _reset_composer(hwnd, box):
    """Remount Slate composer without leaving the channel (replaces
    the manual channel-switch workaround). Rare path; restores cursor."""
    try:
        cur = pyautogui.position()
    except Exception:
        cur = None
    try:
        pyautogui.press("esc")
        time.sleep(0.3)
        r = box.get("rect")
        if r:
            pyautogui.click((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            time.sleep(0.3)
        pyautogui.click(box["x"], box["y"])
        time.sleep(0.4)
    except Exception:
        pass
    try:
        if cur is not None:
            pyautogui.moveTo(cur[0], cur[1])
    except Exception:
        pass


def _restore_window(hwnd):
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
    except Exception:
        pass


def send_one(msg, dry_run=False, keep_focus=False):
    global _jam_count
    target = discord_detector.find_discord_window()
    if not target:
        print("Discord not found. Waiting for Discord app...")
        return False
    hwnd = target["hwnd"]
    box = discord_detector.find_message_box(hwnd)
    if not box:
        print("Discord found but no message box yet (are you in a channel?).")
        return False

    print(
        f"Discord: '{target['title'][:60]}...' "
        f"box={box['method']}@({box['x']},{box['y']}) "
        f"rect={box.get('rect')} scale={box.get('scale')}"
    )

    if dry_run:
        print(f"[dry-run] would type: {msg}")
        return True

    # Don't fight the user for the same box: if Discord itself is
    # focused AND real user input happened since our last auto-send,
    # skip this cycle. (GetLastInputInfo also sees OUR synthetic keys,
    # so ignore idle time that predates our own last send.)
    try:
        if win32gui.GetForegroundWindow() == hwnd and _user_idle_ms() < USER_ACTIVE_MS:
            if _now_tick() - _last_auto_tick > USER_ACTIVE_MS:
                print("You're typing in Discord — skipping this cycle.")
                return False
    except Exception:
        pass

    # NOTE: UIA background send permanently disabled (proven Slate
    # poison: dead-node SetValue, no bubble, keys dead). Focused
    # click-first path below is the only sender.

    # 2) Background focus-borrow path: caret via focus APIs, NO mouse
    # move, NO window activation. Screen stays put, cursor stays put.
    # Physical click is a logged fallback only. Do NOT type in the
    # Discord channel yourself while this runs.
    try:
        cur_pos = pyautogui.position()
    except Exception:
        cur_pos = None
    prev_fg = win32gui.GetForegroundWindow()
    clicked = False
    try:
        _restore_window(hwnd)
        if _jam_count >= 2:
            print("Composer may be jammed — resetting (no channel switch needed).")
            _reset_composer(hwnd, box)
            _jam_count = 0
        # Primary: focus APIs (no mouse, no activation).
        focus_mode = discord_detector.focus_message_box(hwnd)
        if focus_mode:
            print(f"focus placed via {focus_mode} (no mouse, no popup).")
        else:
            print("focus API missed.")
            _jam_count += 1
            if _jam_count < 2:
                print("Retrying next cycle (no keys sent).")
                return False
            # Fallback (logged): one physical click, cursor restored after.
            print("click fallback (cursor will be restored).")
            pyautogui.moveTo(box["x"], box["y"])
            time.sleep(0.3)
            pyautogui.click(box["x"], box["y"])
            clicked = True
            time.sleep(CLICK_SETTLE)
        time.sleep(FOCUS_SETTLE)
        for _mod in ("ctrl", "shift", "alt"):
            try:
                pyautogui.keyUp(_mod)
            except Exception:
                pass
        time.sleep(0.2)
        # Landing guard: if focus is not inside the message input
        # (focus API missed and click hit history/padding), typing
        # blind poisons Slate — faded placeholder stays, keys die.
        # Abort the keystrokes and reset instead.
        try:
            if not discord_detector.is_message_box_focused():
                print("Click missed editable — resetting composer, no keys sent.")
                _reset_composer(hwnd, box)
                _jam_count += 1
                return False
        except Exception:
            pass
        print("landing verified: focus in message box.")
        # First-char gate: type one char, verify Slate recognized it
        # (placeholder hides / value non-empty) before committing the
        # rest + Enter. Unrecognized => abort, never poison the box.
        if not msg:
            return False
        pyautogui.write(msg[0], interval=TYPE_INTERVAL)
        time.sleep(0.4)
        try:
            _in_box, _has_text = discord_detector.focused_box_state()
            if _in_box and _has_text is False:
                print("Slate did not recognize first char — resetting, no Enter sent.")
                _reset_composer(hwnd, box)
                _jam_count += 1
                return False
            if _has_text is None:
                print("gate unknown (value unreadable) — proceeding carefully.")
            else:
                print("gate passed: first char recognized.")
        except Exception as e:
            print(f"gate check failed ({e}) — proceeding carefully.")
        # Human-speed typing (original working behavior): visible
        # char-by-char, single Enter. No bursts, no clipboard, no
        # double-Enter, no Send-click yanking focus mid-submit.
        if len(msg) > 1:
            _type_text(msg[1:])
        time.sleep(WRITE_SETTLE)
        _press_enter()
        time.sleep(ENTER_SETTLE)
        print(f"Sent: {msg}")
        _mark_auto()
        return True
    finally:
        # Cursor: primary path never moves it; restore only if the
        # click fallback moved it.
        try:
            if clicked and cur_pos is not None:
                pyautogui.moveTo(cur_pos[0], cur_pos[1])
        except Exception:
            pass
        # Foreground: focus APIs don't activate, so nothing to restore
        # unless Discord actually became the foreground window.
        if not keep_focus:
            try:
                if win32gui.GetForegroundWindow() == hwnd and win32gui.IsWindow(prev_fg):
                    win32gui.SetForegroundWindow(prev_fg)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description="Auto-type into any open Discord channel.")
    ap.add_argument("--once", action="store_true", help="send wh/wb one time then exit")
    ap.add_argument("--dry-run", action="store_true", help="detect only, don't type")
    ap.add_argument("--keep-focus", action="store_true", help="debug: don't restore previous window after send")
    ap.add_argument("--hover-test", action="store_true", help="move mouse to computed box, no click/type — screenshot to verify")
    ap.add_argument("--focus-test", action="store_true", help="focus box via API only, no mouse/click/type — screenshot caret, 8s")
    ap.add_argument("--notepad-test", action="store_true", help="type wh + Enter into Notepad human-speed (OS-level control, no Discord)")
    args = ap.parse_args()

    if args.notepad_test:
        import subprocess

        print("Opening Notepad in 2s — do not touch keyboard. It will type 'wh' + Enter.")
        time.sleep(2)
        subprocess.Popen(["notepad.exe"])
        time.sleep(1.5)
        _type_text("wh")
        time.sleep(0.6)
        _press_enter()
        time.sleep(0.5)
        _type_text("human-ok")
        print("Notepad test done: you should see 'wh', newline, 'human-ok', typed char-by-char.")
        print("If Enter worked here but not in Discord, keys are fine — it's Discord Slate.")
        return

    if args.focus_test:
        target = discord_detector.find_discord_window()
        if not target:
            print("Discord not found.")
            return
        try:
            before = pyautogui.position()
        except Exception:
            before = None
        mode = discord_detector.focus_message_box(target["hwnd"])
        time.sleep(1.0)
        print(f"focus mode={mode} cursor_before={before} landing={discord_detector.is_message_box_focused()}")
        print("Screenshot now (8s): caret should blink in input, window NOT popped, cursor unmoved.")
        time.sleep(8)
        try:
            after = pyautogui.position()
            print(f"cursor_after={after} moved={before != after}")
        except Exception:
            pass
        return

    if args.hover_test:
        target = discord_detector.find_discord_window()
        if not target:
            print("Discord not found.")
            return
        box = discord_detector.find_message_box(target["hwnd"])
        print(f"Hovering {box['method']}@({box['x']},{box['y']}) rect={box.get('rect')} — screenshot now (10s).")
        pyautogui.moveTo(box["x"], box["y"])
        time.sleep(10)
        print("Hover test done. Was the cursor inside the message input?")
        return

    print("Auto-detect: any open Discord channel message box.")
    print("Use OTHER apps while it runs. Don't type in that Discord")
    print("channel yourself or you'll jam the shared input box.")
    for i in range(STARTUP_DELAY, 0, -1):
        print(f"Starting in {i}s...")
        time.sleep(1)

    if args.once:
        for m in MESSAGES:
            send_one(m, dry_run=args.dry_run, keep_focus=args.keep_focus)
            time.sleep(BETWEEN_MESSAGES_DELAY)
        return

    print("Running. Press Ctrl+C to stop.")
    try:
        while True:
            for m in MESSAGES:
                send_one(m, dry_run=args.dry_run, keep_focus=args.keep_focus)
                time.sleep(BETWEEN_MESSAGES_DELAY)
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            print(f"Waiting {delay:.1f}s... (you're free to use your PC)")
            time.sleep(delay)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
