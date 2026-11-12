"""
Clicker receiver - run this on your friend's computer.

Shows a small window with a pairing code. Whoever has the code can play a
click sound and show text on this screen. Close the window to stop.

    pip install websocket-client
    python receiver.py                      # uses the default server
    python receiver.py wss://clicker.femboy.casino
"""
import json
import math
import os
import queue
import random
import re
import secrets
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.request
import wave

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("Missing dependency. Run:  pip install websocket-client")

DEFAULT_SERVER = "wss://clicker.femboy.casino"
CODE_FILE = os.path.join(os.path.expanduser("~"), ".clicker_code")
TEXT_HIDE_AFTER_MS = 5000


# ---------- pairing code ----------
def load_code():
    try:
        with open(CODE_FILE) as f:
            code = f.read().strip().upper()
            if 4 <= len(code) <= 16 and code.isalnum():
                return code
    except OSError:
        pass
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(alphabet) for _ in range(6))
    try:
        with open(CODE_FILE, "w") as f:
            f.write(code)
    except OSError:
        pass
    return code


# ---------- click sound (generated, no asset needed) ----------
def make_click_wav():
    rate = 44100
    n = int(rate * 0.035)
    rng = random.Random(1)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 220)
        sample = (0.55 * (rng.random() * 2 - 1) + 0.6 * math.sin(2 * math.pi * 2200 * t)) * env
        frames += struct.pack("<h", int(max(-1, min(1, sample)) * 32000))
    path = os.path.join(tempfile.gettempdir(), "clicker_click.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


CLICK_WAV = make_click_wav()
SOUND_DIR = os.path.join(tempfile.gettempdir(), "clicker_sounds")
SOUNDS = []  # local paths of downloaded click sounds; filled by fetch_sounds()


def fetch_sounds(server):
    """Download the server's click sounds once. Falls back to the generated click."""
    base = server.rstrip("/").replace("wss://", "https://", 1).replace("ws://", "http://", 1)
    try:
        with urllib.request.urlopen(f"{base}/sounds", timeout=10) as r:
            names = json.load(r)
    except Exception:
        return
    os.makedirs(SOUND_DIR, exist_ok=True)
    found = []
    for name in names:
        if not re.fullmatch(r"[\w-]+\.(mp3|wav)", str(name)):
            continue
        local = os.path.join(SOUND_DIR, name)
        if not os.path.exists(local):
            try:
                with urllib.request.urlopen(f"{base}/sounds/{name}", timeout=10) as r:
                    data = r.read(2_000_000)
                with open(local, "wb") as f:
                    f.write(data)
            except Exception:
                continue
        found.append(local)
    if found:
        SOUNDS[:] = found


_mci_slot = 0


def _play_windows(path):
    global _mci_slot
    if path == CLICK_WAV:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        return
    # MCI plays mp3 with no extra installs; rotate aliases so rapid clicks overlap
    import ctypes
    mci = ctypes.windll.winmm.mciSendStringW
    alias = f"clk{_mci_slot}"
    _mci_slot = (_mci_slot + 1) % 8
    mci(f"close {alias}", None, 0, None)
    mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
    mci(f"play {alias}", None, 0, None)


def play_click():
    path = random.choice(SOUNDS) if SOUNDS else CLICK_WAV
    if sys.platform == "win32":
        _play_windows(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["afplay", path])
    else:
        players = [["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], ["mpg123", "-q"], ["paplay"], ["aplay", "-q"]]
        for player in players:
            try:
                subprocess.Popen(player + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue


# ---------- network thread ----------
def network_loop(server, code, events):
    url = f"{server.rstrip('/')}/ws?role=receiver&room={code}"
    events.put(("conn", "Downloading sounds..."))
    fetch_sounds(server)
    while True:
        events.put(("conn", "Connecting..."))

        def on_open(ws):
            events.put(("conn", "Connected"))

        def on_message(ws, raw):
            try:
                events.put(("msg", json.loads(raw)))
            except ValueError:
                pass

        def on_error(ws, err):
            events.put(("conn", f"Error: {err}"))

        ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message, on_error=on_error)
        ws.run_forever(ping_interval=20, ping_timeout=10)
        events.put(("conn", "Disconnected, retrying in 3s..."))
        time.sleep(3)


# ---------- start with Windows (HKCU Run key, no admin needed) ----------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ClickerReceiver"
FIRST_RUN_MARKER = os.path.join(os.path.expanduser("~"), ".clicker_startup_asked")


def startup_command(server):
    exe = sys.executable
    # pythonw.exe runs without a console window
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    script = os.path.abspath(__file__)
    return f'"{exe}" "{script}" "{server}" --startup'


def startup_enabled():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except OSError:
        return False


def set_startup(enabled, server):
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, startup_command(server))
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


# ---------- UI ----------
class App:
    def __init__(self, server, launched_at_startup=False):
        self.code = load_code()
        self.server = server

        # turn on start-with-Windows the first time; the checkbox turns it off
        if sys.platform == "win32" and not os.path.exists(FIRST_RUN_MARKER):
            try:
                set_startup(True, server)
                open(FIRST_RUN_MARKER, "w").close()
            except OSError:
                pass
        elif startup_enabled():
            set_startup(True, server)  # refresh the path in case the script moved
        self.events = queue.Queue()
        self.hide_job = None

        # control window (always visible so it's obvious this is running)
        self.root = tk.Tk()
        self.root.title("Clicker receiver")
        self.root.configure(bg="#221b2c", padx=20, pady=16)
        self.root.resizable(False, False)
        fg, muted = "#f3eaf7", "#a493b3"
        tk.Label(self.root, text="Your code", bg="#221b2c", fg=muted, font=("Segoe UI", 10)).pack()
        tk.Label(self.root, text=self.code, bg="#221b2c", fg="#ff7ac6", font=("Consolas", 28, "bold")).pack()
        self.status = tk.Label(self.root, text="Starting...", bg="#221b2c", fg=muted, font=("Segoe UI", 10))
        self.status.pack(pady=(4, 8))
        self.peers = tk.Label(self.root, text="", bg="#221b2c", fg=fg, font=("Segoe UI", 10))
        self.peers.pack()
        if sys.platform == "win32":
            self.startup_var = tk.BooleanVar(value=startup_enabled())
            tk.Checkbutton(self.root, text="Start with Windows", variable=self.startup_var,
                           command=lambda: set_startup(self.startup_var.get(), self.server),
                           bg="#221b2c", fg=fg, selectcolor="#3a2e47", activebackground="#221b2c",
                           activeforeground=fg, font=("Segoe UI", 10)).pack(pady=(8, 0))
        tk.Button(self.root, text="Quit", command=self.root.destroy, bg="#3a2e47", fg=fg,
                  relief="flat", padx=16, pady=4).pack(pady=(10, 0))
        if launched_at_startup:
            self.root.iconify()  # sits in the taskbar instead of popping up on boot

        # overlay window for text
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        try:
            self.overlay.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        self.overlay.configure(bg="#16121c")
        self.text_label = tk.Label(self.overlay, text="", bg="#16121c", fg="#ffffff",
                                   font=("Segoe UI", 32, "bold"), wraplength=900, justify="center",
                                   padx=36, pady=24)
        self.text_label.pack()
        self.overlay.withdraw()

        threading.Thread(target=network_loop, args=(server, self.code, self.events), daemon=True).start()
        self.root.after(30, self.poll)

    def show_text(self, text):
        text = text.strip()
        if not text:
            self.hide_text()
            return
        self.text_label.config(text=text)
        self.overlay.deiconify()
        self.overlay.update_idletasks()
        w, h = self.overlay.winfo_reqwidth(), self.overlay.winfo_reqheight()
        sw, sh = self.overlay.winfo_screenwidth(), self.overlay.winfo_screenheight()
        self.overlay.geometry(f"{w}x{h}+{(sw - w) // 2}+{int(sh * 0.15)}")
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
        self.hide_job = self.root.after(TEXT_HIDE_AFTER_MS, self.hide_text)

    def hide_text(self):
        self.overlay.withdraw()
        self.hide_job = None

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "conn":
                    self.status.config(text=data)
                elif kind == "msg":
                    t = data.get("type")
                    if t == "click":
                        play_click()
                    elif t == "text":
                        self.show_text(str(data.get("text", ""))[:300])
                    elif t == "clear":
                        self.hide_text()
                    elif t == "status":
                        n = data.get("senders", 0)
                        self.peers.config(text=f"{n} sender{'s' if n != 1 else ''} linked")
        except queue.Empty:
            pass
        self.root.after(30, self.poll)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--startup"]
    server = args[0] if args else os.environ.get("CLICKER_SERVER", DEFAULT_SERVER)
    App(server, launched_at_startup="--startup" in sys.argv).run()
