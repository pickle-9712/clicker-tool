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

```
pip install websocket-client
python receiver.py                                # defaults to wss://clicker.femboy.casino
python receiver.py ws://localhost:8787            # for local testing
```
A small window shows their code (for example `K7QX2M`). The code is saved in `~/.clicker_code`, so it stays the same between runs. Closing the window stops everything.

### Starts with Windows

The first time the receiver runs it turns on **Start with Windows** (an entry under
`HKCU\...\CurrentVersion\Run` — no admin needed) and ticks the matching checkbox in its window.
Your friend can untick it any time to turn it off. On a boot-up launch the window starts minimized
to the taskbar instead of popping up. Nothing is installed system-wide, so removing the folder and
unticking the box leaves no trace.

## 4. You

Two ways to drive it:

**App (recommended).** Double-click `sender/sender.pyw` — a dark control window opens, no browser
needed (needs `pip install websocket-client`, same as the receiver). It remembers the last code and
server. The **Server** box lets you point it at `ws://localhost:8787` for local testing.

**Browser.** Open https://clicker.femboy.casino, enter their code, and click **Link**.

Either way:
- **CLICK** button (or press Space) plays a random sound from `server/public/sounds/` on their end. To add or remove sounds, drop `.mp3`/`.wav` files in or out of that folder. The receiver downloads them when it starts. If it can't reach them, it plays a built-in click instead.
- Type in the box. With **Live** on, the text updates as you type. It disappears 5 s after your last keystroke, or right away when you press **Clear**.
