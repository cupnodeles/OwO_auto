"""Detect Discord app window + its message box (any open channel).

Discord desktop is Electron/Chromium so its chat input is NOT exposed
as a Win32 EDIT control unless Discord is launched with
--force-renderer-accessibility. This module therefore:

1. Finds the Discord main window (Chrome_WidgetWin_1 + 'Discord' title).
2. Tries UIA to find a control named 'Message #...' (any open channel).
3. Falls back to an estimated input rect (bottom-center of window) so the
   typer can still click/type ONLY inside Discord's message box.
"""

import ctypes

import psutil
import win32api
import win32gui
import win32process

DISCORD_CLASS = "Chrome_WidgetWin_1"


def _dpi_scale(hwnd):
    try:
        get_dpi = ctypes.windll.shcore.GetDpiForWindow
        get_dpi.restype = ctypes.c_uint
        return get_dpi(hwnd) / 96.0
    except Exception:
        return 1.0


def _client_rect(hwnd):
    """Client-area rect in screen coords (excludes borders/titlebar)."""
    try:
        left, top = win32gui.ClientToScreen(hwnd, (0, 0))
        right, bottom = win32gui.ClientToScreen(
            hwnd, (win32gui.GetClientRect(hwnd)[2], win32gui.GetClientRect(hwnd)[3])
        )
        return (left, top, right, bottom)
    except Exception:
        return win32gui.GetWindowRect(hwnd)


def _is_discord_process(hwnd):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        name = psutil.Process(pid).name().lower()
        return "discord" in name
    except Exception:
        return False


def find_discord_window():
    """Return {'hwnd': int, 'title': str, 'rect': (l,t,r,b)} or None."""
    found = []

    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            if win32gui.GetClassName(hwnd) != DISCORD_CLASS:
                return
            title = win32gui.GetWindowText(hwnd)
            if "discord" not in title.lower():
                return
            if not _is_discord_process(hwnd):
                return
            try:
                rect = win32gui.GetWindowRect(hwnd)
            except Exception:
                return
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w < 400 or h < 300:  # skip tiny popouts/tray ghosts
                return
            found.append({"hwnd": hwnd, "title": title, "rect": rect})
        except Exception:
            return

    win32gui.EnumWindows(cb, None)
    if not found:
        return None
    # Prefer the main window: longest title ending with '- Discord'.
    found.sort(key=lambda d: len(d["title"]), reverse=True)
    return found[0]


def find_message_box(hwnd):
    """Find chat input for whatever channel is currently open.

    Returns {'x': int, 'y': int, 'method': 'uia'|'estimated', 'name': str}
    or None if the Discord window itself is gone.
    """
    try:
        rect = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None
    left, top, right, bottom = rect

    # 1) Try real UIA detection (works if Discord exposes accessibility).
    try:
        import uiautomation as auto

        win = auto.ControlFromHandle(hwnd)
        stack = [(win, 0)]
        seen = 0
        while stack and seen < 8000:
            ctrl, depth = stack.pop()
            try:
                children = ctrl.GetChildren()
            except Exception:
                continue
            for c in children:
                seen += 1
                try:
                    name = c.Name or ""
                    if "message #" in name.lower() or name.lower().startswith("message @"):
                        try:
                            r = c.BoundingRect
                            cx = (r.left + r.right) // 2
                            cy = (r.top + r.bottom) // 2
                        except Exception:
                            continue
                        return {
                            "x": cx,
                            "y": cy,
                            "method": "uia",
                            "name": name,
                            "rect": _client_rect(hwnd),
                            "scale": _dpi_scale(hwnd),
                            "send_x": cx + 120,
                            "send_y": cy,
                        }
                except Exception:
                    pass
                if depth < 15:
                    stack.append((c, depth + 1))
    except Exception:
        pass

    # 2) Fallback: estimated input box from CLIENT rect (no borders).
    # Calibrated from fullscreen 1920x1080 screenshot: input bar center
    # sits in the left-half textbox (~35% from client left, clear of
    # GIF/sticker/send buttons) and ~32px (DPI-scaled) above client
    # bottom. Old 0.42/85px landed ~50px too high in message history.
    try:
        cle, cto, cri, cbo = _client_rect(hwnd)
    except Exception:
        return None
    scale = _dpi_scale(hwnd)
    cw = cri - cle
    ch = cbo - cto
    cx = int(cle + cw * 0.35)
    cy = int(cbo - 32 * scale)
    send_x = int(cle + cw * 0.86)
    send_y = cy
    rect = (cle, cto, cri, cbo)
    return {
        "x": cx,
        "y": cy,
        "method": "estimated",
        "name": "estimated-input-bar",
        "rect": rect,
        "scale": round(scale, 2),
        "send_x": send_x,
        "send_y": send_y,
    }


def is_message_box_focused():
    """True if keyboard focus is inside Discord's message input."""
    try:
        import uiautomation as auto

        f = auto.GetFocusedControl()
        name = (f.Name or "").lower()
        return "message #" in name or name.startswith("message @")
    except Exception:
        return False


def focused_box_state():
    """Click-first gate probe: (in_box, has_text).

    in_box: focus is inside Discord's message input.
    has_text: focused input holds text (None = unreadable, proceed).
    """
    try:
        import uiautomation as auto

        f = auto.GetFocusedControl()
        name = (f.Name or "")
        low = name.lower()
        in_box = ("message #" in low) or low.startswith("message @")
        if not in_box:
            return (False, None)
        try:
            val = f.GetValuePattern().Value
            return (True, bool(val and val.strip()))
        except Exception:
            return (True, None)
    except Exception:
        return (False, None)


def find_message_element(hwnd):
    """Return the UIA 'Message #...' control itself (or None).

    Same walk the old background sender used — the element exists,
    only SetValue on it was poison. Used for SetFocus (caret, no mouse).
    """
    try:
        import uiautomation as auto

        win = auto.ControlFromHandle(hwnd)
        stack = [win]
        seen = 0
        while stack and seen < 8000:
            ctrl = stack.pop()
            try:
                children = ctrl.GetChildren()
            except Exception:
                continue
            for c in children:
                seen += 1
                try:
                    name = c.Name or ""
                    if "message #" in name.lower() or name.lower().startswith("message @"):
                        return c
                except Exception:
                    pass
                stack.append(c)
    except Exception:
        pass
    return None


def focus_message_box(hwnd):
    """Place caret in Discord's input WITHOUT mouse or activation.

    Returns 'uia' (control SetFocus), 'thread' (attached SetFocus),
    or None. Screen stays put, cursor never moves.
    """
    try:
        el = find_message_element(hwnd)
        if el is not None:
            try:
                el.SetFocus()
                return "uia"
            except Exception:
                pass
    except Exception:
        pass
    try:
        user32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        tid_mine = k32.GetCurrentThreadId()
        tid_discord = win32process.GetWindowThreadProcessId(hwnd)[0]
        user32.AttachThreadInput(tid_mine, tid_discord, True)
        try:
            if user32.SetFocus(hwnd):
                return "thread"
        finally:
            user32.AttachThreadInput(tid_mine, tid_discord, False)
    except Exception:
        pass
    return None


def try_uia_background_send(hwnd, text):
    """DISABLED (proven poison 2026-09-27): SetValue writes a dead DOM node,
    Slate model stays empty — no bubble, OwO silent, keys dead until
    channel-switch. Focus path is the only sender.
    Kept as stub so old call sites fail safe (False)."""
    return False
