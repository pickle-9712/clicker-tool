"""
Clicker sender - the control panel you run on your own computer.
Double-click this file (.pyw means no console window opens).

    pip install websocket-client
"""
import json
import os
import queue
import re
import sys
import threading
import tkinter as tk

try:
    import websocket  # websocket-client
except ImportError:
    tk.Tk().withdraw()
    import tkinter.messagebox as mb
    mb.showerror("Clicker", "Missing dependency.\n\nRun:  pip install websocket-client")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glass

DEFAULT_SERVER = "wss://clicker.femboy.casino"
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".clicker_sender.json")

# translucent palette (sits over the acrylic blur)
BG, CARD, FIELD, BORDER = "#1a1420", "#2a2136", "#140f19", "#4a3b5c"
FG, MUTED, ACCENT, ACCENT2, OK, BAD = "#f3eaf7", "#b9a8c8", "#ff7ac6", "#ffa6d6", "#6be19a", "#ff6b6b"
FONT = "Segoe UI"
GLASS_TINT = 0xD8241A2E  # 0xAABBGGRR


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


class Connection:
    """Keeps one sender websocket alive in a background thread, reconnecting as needed."""

    def __init__(self, events):
        self.events = events
        self.ws = None
        self.generation = 0  # bumps each (re)connect; stale threads exit

    def connect(self, server, room):
        self.generation += 1
        gen = self.generation
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        threading.Thread(target=self._run, args=(gen, server, room), daemon=True).start()

    def _run(self, gen, server, room):
        import time
        url = f"{server.rstrip('/')}/ws?role=sender&room={room}"
        while gen == self.generation:
            self.events.put(("conn", "Connecting..."))
            ws = websocket.WebSocketApp(
                url,
                on_open=lambda w: self.events.put(("conn", "open")),
                on_message=lambda w, m: self._on_msg(m),
                on_error=lambda w, e: self.events.put(("conn", f"Error: {e}")),
            )
            self.ws = ws
            ws.run_forever(ping_interval=20, ping_timeout=10)
            if gen != self.generation:
                return
            self.events.put(("conn", "Disconnected, retrying..."))
            time.sleep(2)

    def _on_msg(self, raw):
        try:
            self.events.put(("msg", json.loads(raw)))
        except ValueError:
            pass

    def send(self, obj):
        try:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(obj))
        except Exception:
            pass


def hover(widget, normal, over):
    widget.bind("<Enter>", lambda e: widget.config(bg=over))
    widget.bind("<Leave>", lambda e: widget.config(bg=normal))


class App:
    def __init__(self):
        self.settings = load_settings()
        self.events = queue.Queue()
        self.conn = Connection(self.events)
        self.friend_online = False
        self.mini = bool(self.settings.get("mini", False))
        self.clicks = 0

        self.root = tk.Tk()
        self.root.title("Clicker")
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)
        self.root.attributes("-alpha", 0.0)
        self.root.geometry("+%d+%d" % (self.settings.get("x", 360), self.settings.get("y", 220)))

        glass.enable_glass(self.root, tint=GLASS_TINT)
        glass.show_in_taskbar(self.root)

        self.container = tk.Frame(self.root, bg=BG)
        self.container.pack(fill="both", expand=True)

        self._build_titlebar()
        self._build_full()
        self._build_mini()

        self.root.bind("<KeyPress-space>", self._space_click)
        self.root.bind("<Escape>", lambda e: self.close())
        self.root.after(30, self.poll)

        self._apply_mode(animate=False)
        if self.settings.get("room", "").strip():
            self.link()
        glass.fade_in(self.root, target=0.94)

    # ---------- chrome ----------
    def _build_titlebar(self):
        self.bar = tk.Frame(self.container, bg=BG, height=38)
        self.bar.pack(fill="x")
        self.bar.pack_propagate(False)
        self.title_lbl = tk.Label(self.bar, text="  Clicker", bg=BG, fg=FG, font=(FONT, 11, "bold"))
        self.title_lbl.pack(side="left", padx=(6, 0))
        glass.make_draggable(self.root, self.bar)
        glass.make_draggable(self.root, self.title_lbl)

        for text, cmd, col in (("✕", self.close, BAD), ("–", self.minimize, FG),
                               ("□", self.toggle_mini, ACCENT)):
            b = tk.Label(self.bar, text=text, bg=BG, fg=col, font=(FONT, 12), width=3, cursor="hand2")
            b.pack(side="right")
            b.bind("<Button-1>", lambda e, c=cmd: c())
            hover(b, BG, BORDER)
        self.mode_btn = self.bar.pack_slaves()[-1]  # the mode toggle, for relabeling

    def _card(self, parent):
        c = tk.Frame(parent, bg=CARD)
        c.pack(fill="x", padx=14, pady=(0, 12))
        inner = tk.Frame(c, bg=CARD)
        inner.pack(fill="x", padx=14, pady=12)
        return inner

    # ---------- full UI ----------
    def _build_full(self):
        self.full = tk.Frame(self.container, bg=BG)

        link = self._card(self.full)
        tk.Label(link, text="Friend's code", bg=CARD, fg=MUTED, font=(FONT, 10)).pack(anchor="w")
        row = tk.Frame(link, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        self.room = tk.Entry(row, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                             font=(FONT, 14), justify="center")
        self.room.pack(side="left", fill="x", expand=True, ipady=6)
        self.room.insert(0, self.settings.get("room", ""))
        self.room.bind("<Return>", lambda e: self.link())
        self.link_btn = tk.Label(row, text="Link", bg=BORDER, fg=FG, font=(FONT, 11), padx=16, pady=6, cursor="hand2")
        self.link_btn.pack(side="left", padx=(8, 0))
        self.link_btn.bind("<Button-1>", lambda e: self.link())
        hover(self.link_btn, BORDER, ACCENT)
        self.status = tk.Label(link, text="Not linked", bg=CARD, fg=MUTED, font=(FONT, 10))
        self.status.pack(anchor="w", pady=(10, 0))
        srow = tk.Frame(link, bg=CARD)
        srow.pack(fill="x", pady=(8, 0))
        tk.Label(srow, text="Server", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.server = tk.Entry(srow, bg=FIELD, fg=MUTED, insertbackground=FG, relief="flat", font=(FONT, 9))
        self.server.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=3)
        self.server.insert(0, self.settings.get("server", DEFAULT_SERVER))

        self.click_btn = tk.Label(self.full, text="CLICK", bg=ACCENT, fg="#2a0b1d",
                                  font=(FONT, 22, "bold"), pady=20, cursor="hand2")
        self.click_btn.pack(fill="x", padx=14)
        self.click_btn.bind("<Button-1>", lambda e: self.click())
        tk.Label(self.full, text="or press Space", bg=BG, fg=MUTED, font=(FONT, 9)).pack(pady=(4, 10))

        tcard = self._card(self.full)
        tk.Label(tcard, text="Text on their screen", bg=CARD, fg=MUTED, font=(FONT, 10)).pack(anchor="w")
        self.text = tk.Text(tcard, height=3, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                            font=(FONT, 12), wrap="word", highlightthickness=0)
        self.text.pack(fill="x", pady=(6, 0))
        self.text.bind("<KeyRelease>", self._on_type)
        self.text.bind("<Return>", self._on_enter)
        self.live = tk.BooleanVar(value=self.settings.get("live", True))
        tk.Checkbutton(tcard, text="Live (show as I type)", variable=self.live, bg=CARD, fg=MUTED,
                       selectcolor=BORDER, activebackground=CARD, activeforeground=MUTED,
                       font=(FONT, 9)).pack(anchor="w", pady=(6, 0))
        brow = tk.Frame(tcard, bg=CARD)
        brow.pack(fill="x", pady=(8, 0))
        for text, cmd in (("Send", self.send_text), ("Clear their screen", self.clear)):
            b = tk.Label(brow, text=text, bg=BORDER, fg=FG, font=(FONT, 11), padx=14, pady=5, cursor="hand2")
            b.pack(side="left", padx=(0, 8))
            b.bind("<Button-1>", lambda e, c=cmd: c())
            hover(b, BORDER, ACCENT)

    # ---------- clicker-only UI ----------
    def _build_mini(self):
        self.minf = tk.Frame(self.container, bg=BG)
        self.pad = tk.Label(self.minf, text="CLICK", bg=ACCENT, fg="#2a0b1d",
                            font=(FONT, 30, "bold"), width=8, height=3, cursor="hand2")
        self.pad.pack(padx=18, pady=(2, 10))
        self.pad.bind("<Button-1>", lambda e: self.click())
        self.mini_status = tk.Label(self.minf, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.mini_status.pack(pady=(0, 10))

    # ---------- mode switching ----------
    def toggle_mini(self):
        self.mini = not self.mini
        self._apply_mode(animate=True)

    def _apply_mode(self, animate):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.full.pack_forget()
        self.minf.pack_forget()
        if self.mini:
            self.minf.pack(fill="both", expand=True)
            self.mode_btn.config(text="▣")  # filled square = expand back
        else:
            self.full.pack(fill="both", expand=True)
            self.mode_btn.config(text="□")
        self.root.geometry("")  # shrink-wrap to the visible content
        self.root.update_idletasks()
        self.root.geometry("+%d+%d" % (x, y))
        glass.enable_glass(self.root, tint=GLASS_TINT)  # reassert after resize
        self._refresh_status()

    # ---------- actions ----------
    def link(self):
        code = self.room.get().strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{4,16}", code):
            self.status.config(text="Code should be 4-16 letters/numbers", fg=BAD)
            return
        self.room.delete(0, "end")
        self.room.insert(0, code)
        server = self.server.get().strip() or DEFAULT_SERVER
        self._save()
        self.status.config(text="Connecting...", fg=MUTED)
        self.conn.connect(server, code)

    def _set_online(self, online):
        self.friend_online = online
        self._refresh_status()

    def _refresh_status(self):
        code = self.room.get().strip().upper() if hasattr(self, "room") else ""
        if self.friend_online:
            self.status.config(text=f"Linked to {code} - friend online", fg=OK)
            self.pad.config(bg=ACCENT)
            self.mini_status.config(text=f"{self.clicks} sent  -  {code}", fg=MUTED)
        else:
            self.status.config(text=f"Joined {code} - waiting..." if code else "Not linked", fg=MUTED)
            self.pad.config(bg=BORDER)
            self.mini_status.config(text="waiting for friend..." if code else "not linked", fg=MUTED)

    def click(self):
        if not self.friend_online:
            return
        self.conn.send({"type": "click"})
        self.clicks += 1
        target = self.pad if self.mini else self.click_btn
        target.config(bg=ACCENT2)
        self.root.after(90, lambda: target.config(bg=ACCENT))
        if self.mini:
            self.mini_status.config(text=f"{self.clicks} sent", fg=OK)

    def _space_click(self, e):
        if not isinstance(self.root.focus_get(), (tk.Text, tk.Entry)):
            self.click()
            return "break"

    def _on_type(self, e):
        if self.live.get():
            self.conn.send({"type": "text", "text": self.text.get("1.0", "end-1c")[:300]})

    def _on_enter(self, e):
        if not (e.state & 0x0001):  # not Shift+Enter
            self.send_text()
            if not self.live.get():
                self.text.delete("1.0", "end")
            return "break"

    def send_text(self):
        self.conn.send({"type": "text", "text": self.text.get("1.0", "end-1c")[:300]})

    def clear(self):
        self.text.delete("1.0", "end")
        self.conn.send({"type": "clear"})

    # ---------- window ----------
    def minimize(self):
        glass.minimize(self.root)

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "conn" and data != "open":
                    self.status.config(text=data, fg=MUTED)
                elif kind == "msg" and data.get("type") == "status":
                    self._set_online(data.get("receivers", 0) > 0)
        except queue.Empty:
            pass
        self.root.after(30, self.poll)

    def _save(self):
        save_settings({
            "room": self.room.get().strip().upper(),
            "server": self.server.get().strip() or DEFAULT_SERVER,
            "live": self.live.get(), "mini": self.mini,
            "x": self.root.winfo_x(), "y": self.root.winfo_y(),
        })

    def close(self):
        self._save()
        glass.fade_out(self.root, on_done=self.root.destroy)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
