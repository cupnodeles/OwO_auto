"""OwO Farm Control Panel — tkinter popup in OwO's cow/pink/dark style.

Fields: Server (guild ID or discord.gg invite), Channel (ID),
Commands (default wh, wb — add/remove/reorder), delays + gap.
Buttons: Save, Setup login, Check, Once, Start/Stop the minimized
browser farmer. Settings live in config.json (local, gitignored).

Run:  python owo_ui.py
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "config.json")
BROWSER_TYPER = os.path.join(HERE, "discord_browser_typer.py")

# OwO look: dark Discord greys + cow-pink accents.
BG = "#2b2d31"
PANEL = "#313338"
ENTRY_BG = "#1e1f22"
PINK = "#ff9ecd"
PINK_DARK = "#e06fa8"
TEXT = "#ffffff"
MUTED = "#b5bac1"

DEFAULTS = {
    "server": "",
    "channel": "",
    "commands": ["wh", "wb"],
    "min_delay": "11",
    "max_delay": "19",
    "gap": "0.6",
}


def resolve_guild_id(server_text):
    """Accept a guild ID or an invite; return guild ID or raise ValueError."""
    s = (server_text or "").strip()
    if re.fullmatch(r"\d{10,}", s):
        return s
    m = re.search(r"(?:discord\.gg/|discord\.com/invite/)([A-Za-z0-9-]+)", s)
    code = m.group(1) if m else (s if re.fullmatch(r"[A-Za-z0-9-]{2,}", s) else None)
    if not code:
        raise ValueError("Server must be a guild ID or an invite link/code.")
    import urllib.request

    req = urllib.request.Request(
        f"https://discord.com/api/v9/invites/{code}",
        headers={"User-Agent": "OwO-Farm-Panel"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        return str(data["guild"]["id"])
    except Exception:
        raise ValueError(f"Could not resolve invite '{code}' (invalid/expired?).")


def build_url(guild_id, channel_id):
    channel_id = (channel_id or "").strip()
    if not re.fullmatch(r"\d{10,}", channel_id):
        raise ValueError("Channel must be a numeric channel ID.")
    return f"https://discord.com/channels/{guild_id}/{channel_id}"


class Panel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🐄 OwO Farm Control")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.proc = None
        self.log_q = queue.Queue()
        self.cfg = dict(DEFAULTS)
        self._load()

        tk.Label(self, text="🐄 OwO Farm Control", bg=BG, fg=PINK,
                 font=("Segoe UI", 16, "bold")).pack(pady=(12, 0))
        tk.Label(self, text="Hewwo! pick your farm spot ✿", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "italic")).pack(pady=(0, 8))

        body = tk.Frame(self, bg=PANEL, padx=14, pady=12)
        body.pack(padx=12, pady=4, fill="x")

        self.server_var = tk.StringVar(value=self.cfg["server"])
        self.channel_var = tk.StringVar(value=self.cfg["channel"])
        self._row(body, 0, "Server (ID/invite)", self.server_var)
        self._row(body, 1, "Channel (ID)", self.channel_var)

        tk.Label(body, text="Commands (in order)", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=(8, 2))
        self.cmd_list = tk.Listbox(body, bg=ENTRY_BG, fg=TEXT, selectbackground=PINK_DARK,
                                   height=4, width=28, relief="flat", highlightthickness=0)
        self.cmd_list.grid(row=3, column=0, sticky="w")
        for c in self.cfg["commands"]:
            self.cmd_list.insert("end", c)
        side = tk.Frame(body, bg=PANEL)
        side.grid(row=3, column=1, sticky="n", padx=(8, 0))
        self.cmd_entry = tk.Entry(side, bg=ENTRY_BG, fg=TEXT, width=12,
                                  relief="flat", insertbackground=PINK)
        self.cmd_entry.pack(pady=2)
        for label, fn in (("＋ Add", self._cmd_add), ("－ Remove", self._cmd_del),
                          ("▲ Up", self._cmd_up), ("▼ Down", self._cmd_down)):
            tk.Button(side, text=label, bg=ENTRY_BG, fg=PINK, relief="flat",
                      width=10, command=fn, activebackground=PINK_DARK,
                      activeforeground=TEXT).pack(pady=1)

        trow = tk.Frame(body, bg=PANEL)
        trow.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.min_var = tk.StringVar(value=self.cfg["min_delay"])
        self.max_var = tk.StringVar(value=self.cfg["max_delay"])
        self.gap_var = tk.StringVar(value=self.cfg["gap"])
        for label, var in (("Min s", self.min_var), ("Max s", self.max_var), ("Gap s", self.gap_var)):
            tk.Label(trow, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
            tk.Entry(trow, textvariable=var, bg=ENTRY_BG, fg=TEXT, width=6,
                     relief="flat", insertbackground=PINK).pack(side="left", padx=(2, 10))

        brow = tk.Frame(self, bg=BG)
        brow.pack(pady=10)
        self.save_b = self._btn(brow, "💾 Save", self._save)
        self._btn(brow, "🔑 Setup", lambda: self._run(["--setup"], long=True))
        self._btn(brow, "🔍 Check", lambda: self._run(["--check"]))
        self._btn(brow, "✉ Once", lambda: self._run(["--once"]))
        self.toggle_b = self._btn(brow, "▶ Start", self._toggle)

        self.log = tk.Text(self, bg=ENTRY_BG, fg=TEXT, height=10, width=58,
                           relief="flat", state="disabled", font=("Consolas", 8))
        self.log.pack(padx=12, pady=(0, 12))
        self.after(200, self._pump)

    def _btn(self, parent, text, fn):
        b = tk.Button(parent, text=text, bg=PINK, fg="#2b2d31", relief="flat",
                      font=("Segoe UI", 9, "bold"), padx=8, pady=4,
                      activebackground=PINK_DARK, command=fn)
        b.pack(side="left", padx=4)
        return b

    def _row(self, parent, r, label, var):
        tk.Label(parent, text=label, bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", pady=2)
        tk.Entry(parent, textvariable=var, bg=ENTRY_BG, fg=TEXT, width=34,
                 relief="flat", insertbackground=PINK).grid(row=r, column=1, padx=(8, 0), pady=2)

    # ---- commands list ----
    def _cmds(self):
        return [self.cmd_list.get(i) for i in range(self.cmd_list.size())]

    def _cmd_add(self):
        v = self.cmd_entry.get().strip()
        if v:
            self.cmd_list.insert("end", v)
            self.cmd_entry.delete(0, "end")

    def _cmd_del(self):
        for i in reversed(self.cmd_list.curselection()):
            self.cmd_list.delete(i)

    def _cmd_up(self):
        for i in self.cmd_list.curselection():
            if i > 0:
                v = self.cmd_list.get(i)
                self.cmd_list.delete(i)
                self.cmd_list.insert(i - 1, v)
                self.cmd_list.selection_set(i - 1)

    def _cmd_down(self):
        for i in reversed(self.cmd_list.curselection()):
            if i < self.cmd_list.size() - 1:
                v = self.cmd_list.get(i)
                self.cmd_list.delete(i)
                self.cmd_list.insert(i + 1, v)
                self.cmd_list.selection_set(i + 1)

    # ---- config ----
    def _collect(self):
        cmds = self._cmds()
        if not cmds:
            raise ValueError("Add at least one command (default: wh, wb).")
        guild = resolve_guild_id(self.server_var.get())
        url = build_url(guild, self.channel_var.get())
        return {
            "server": self.server_var.get().strip(),
            "channel": self.channel_var.get().strip(),
            "commands": cmds,
            "min_delay": self.min_var.get().strip() or "11",
            "max_delay": self.max_var.get().strip() or "19",
            "gap": self.gap_var.get().strip() or "0.6",
            "url": url,
            "guild_id": guild,
        }

    def _save(self, silent=False):
        try:
            cfg = self._collect()
        except ValueError as e:
            if not silent:
                messagebox.showerror("OwO says no ✿", str(e))
            return None
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({k: cfg[k] for k in
                       ("server", "channel", "commands", "min_delay", "max_delay", "gap")},
                      f, indent=2)
        self._log(f"💾 Saved — URL resolves, channel ID ok. Cowoncy awaits! 🐄")
        return cfg

    def _load(self):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                self.cfg.update(json.load(f))
            if isinstance(self.cfg.get("commands"), list) and self.cfg["commands"]:
                pass
            else:
                self.cfg["commands"] = list(DEFAULTS["commands"])
        except Exception:
            pass

    # ---- runner ----
    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _pump(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                self._log(line.rstrip())
        except queue.Empty:
            pass
        if self.proc is not None and self.proc.poll() is not None:
            self._log(f"■ Process ended (code {self.proc.returncode}).")
            self.proc = None
            self.toggle_b.configure(text="▶ Start")
        self.after(200, self._pump)

    def _run(self, args, long=False):
        if self.proc is not None:
            messagebox.showinfo("OwO", "A run is already active — Stop it first! 🐄")
            return
        cfg = self._save(silent=False)
        if cfg is None:
            return
        env = dict(os.environ)
        env["DISCORD_CHANNEL_URL"] = cfg["url"]
        env["OWO_COMMANDS"] = ",".join(cfg["commands"])
        env["OWO_MIN_DELAY"] = cfg["min_delay"]
        env["OWO_MAX_DELAY"] = cfg["max_delay"]
        env["OWO_GAP"] = cfg["gap"]
        if long:
            messagebox.showinfo("OwO", "Log in inside the Chromium window,\nthen press Enter in the black terminal! 🐄")
        try:
            self.proc = subprocess.Popen(
                [sys.executable, BROWSER_TYPER] + args, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
        except Exception as e:
            messagebox.showerror("OwO says no ✿", f"Could not start:\n{e}")
            return
        if args == []:
            self.toggle_b.configure(text="■ Stop")
        threading.Thread(target=self._drain, daemon=True).start()
        self._log(f"▶ Started {' '.join(args) or 'loop'} — {','.join(cfg['commands'])}")

    def _drain(self):
        try:
            for line in self.proc.stdout:
                self.log_q.put(line)
        except Exception:
            pass

    def _toggle(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self._log("■ Stopping…")
        else:
            self._run([])


def main():
    Panel().mainloop()


if __name__ == "__main__":
    main()
