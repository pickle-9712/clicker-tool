# Clicker

Press a button → your friend's computer plays a click. Type → text appears on their screen.

```
 you (browser)  ──wss──▶  relay server (clicker.femboy.casino)  ──wss──▶  friend (receiver.py)
```

## 1. Run the relay

```
cd server
npm install
npm start          # listens on http://localhost:8787  (PORT env var to change)
```

## 2. Put it on your domain

Pick one:

**A. Cloudflare Tunnel from your own PC (free, no port forwarding).** The domain needs to use Cloudflare DNS.
```
winget install Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create clicker
cloudflared tunnel route dns clicker clicker.femboy.casino
cloudflared tunnel run --url http://localhost:8787 clicker
```
This only works while your PC is on and both `npm start` and `cloudflared` are running.

**B. A VPS (always on).** Copy `server/` over, run it with `pm2` or systemd, and put Caddy in front:
```
clicker.femboy.casino {
    reverse_proxy localhost:8787
}
```
Caddy sets up HTTPS for you, and WebSockets work with no extra config.

## 3. Friend runs the receiver

Easiest: give them **ClickerReceiver.exe** from the [Releases page](https://github.com/pickle-9712/clicker-tool/releases) — no Python needed. Or from source:

```
pip install websocket-client
python receiver.py
```
The server is hardcoded to `wss://clicker.femboy.casino`; there's nothing to configure. A small window shows their code (for example `K7QX2M`). The code is saved in `~/.clicker_code`, so it stays the same between runs. Closing the window stops everything.

> Local testing only: set the `CLICKER_SERVER` environment variable (e.g. `ws://localhost:8787`) before launching either side to point it at a local relay.

### Starts with Windows

The first time the receiver runs it turns on **Start with Windows** (an entry under
`HKCU\...\CurrentVersion\Run` — no admin needed) and ticks the matching checkbox in its window.
Your friend can untick it any time to turn it off. On a boot-up launch the window starts minimized
to the taskbar instead of popping up. Nothing is installed system-wide, so removing the folder and
unticking the box leaves no trace.

## 4. You

Two ways to drive it:

**App (recommended).** Run **ClickerSender.exe** from the [Releases page](https://github.com/pickle-9712/clicker-tool/releases), or `pythonw sender/sender.pyw` from source. A frosted-glass control window opens — enter your friend's code and **Link**. The `□` button in the title bar collapses it to a **clicker-only** pad; `▣` expands it back. It always connects to `wss://clicker.femboy.casino`.

**Browser.** Open https://clicker.femboy.casino, enter their code, and click **Link**.

Either way:
- **CLICK** button (or press Space) plays a random sound from `server/public/sounds/` on their end. To add or remove sounds, drop `.mp3`/`.wav` files in or out of that folder. The receiver downloads them when it starts. If it can't reach them, it plays a built-in click instead.
- Type in the box. With **Live** on, the text updates as you type. It disappears 5 s after your last keystroke, or right away when you press **Clear**.
