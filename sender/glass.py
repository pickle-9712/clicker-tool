"""
Frosted-glass helpers for Tkinter on Windows 11.

enable_glass()  - acrylic blur behind the window + rounded corners
fade_in/out()   - open/close animations (alpha + a little slide)
make_draggable()- drag a borderless window by any widget
minimize()      - minimize a borderless window to the taskbar

Everything degrades gracefully (no-ops) off Windows.
"""
import sys
import tkinter as tk

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _dwm = ctypes.windll.dwmapi

    class _ACCENTPOLICY(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_uint), ("AccentFlags", ctypes.c_uint),
                    ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_uint)]

    class _WINCOMPATTR(ctypes.Structure):
        _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]

    _ACCENT_ACRYLIC = 4
    _ACCENT_BLUR = 3
    _WCA_ACCENT_POLICY = 19
    _GA_ROOT = 2
    _GWL_EXSTYLE = -20
    _GWL_STYLE = -16
    _WS_EX_APPWINDOW = 0x00040000
    _WS_EX_TOOLWINDOW = 0x00000080
    _WS_MINIMIZEBOX = 0x00020000
    _SW_MINIMIZE = 6

    _getlong = _user32.GetWindowLongPtrW if hasattr(_user32, "GetWindowLongPtrW") else _user32.GetWindowLongW
    _setlong = _user32.SetWindowLongPtrW if hasattr(_user32, "SetWindowLongPtrW") else _user32.SetWindowLongW

    def _hwnd(win):
        win.update_idletasks()
        return _user32.GetAncestor(win.winfo_id(), _GA_ROOT)

    def enable_glass(win, tint=0xE61C1216, acrylic=True):
        """tint is 0xAABBGGRR. Big alpha = more solid, small = more see-through."""
        hwnd = _hwnd(win)
        accent = _ACCENTPOLICY()
        accent.AccentState = _ACCENT_ACRYLIC if acrylic else _ACCENT_BLUR
        accent.GradientColor = tint
        data = _WINCOMPATTR()
        data.Attribute = _WCA_ACCENT_POLICY
        data.SizeOfData = ctypes.sizeof(accent)
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        try:
            _user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        except Exception:
            pass
        # Windows 11 rounded corners: DWMWA_WINDOW_CORNER_PREFERENCE(33) = DWMWCP_ROUND(2)
        try:
            _dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int))
        except Exception:
            pass

    def show_in_taskbar(win):
        hwnd = _hwnd(win)
        ex = _getlong(hwnd, _GWL_EXSTYLE)
        ex = (ex | _WS_EX_APPWINDOW) & ~_WS_EX_TOOLWINDOW
        _setlong(hwnd, _GWL_EXSTYLE, ex)
        _setlong(hwnd, _GWL_STYLE, _getlong(hwnd, _GWL_STYLE) | _WS_MINIMIZEBOX)

    def minimize(win):
        _user32.ShowWindow(_hwnd(win), _SW_MINIMIZE)

else:  # non-Windows fallbacks
    def enable_glass(win, tint=None, acrylic=True):
        try:
            win.attributes("-alpha", 0.95)
        except tk.TclError:
            pass

    def show_in_taskbar(win):
        pass

    def minimize(win):
        try:
            win.iconify()
        except tk.TclError:
            pass


def _set_alpha(win, a):
    try:
        win.attributes("-alpha", max(0.0, min(1.0, a)))
    except tk.TclError:
        pass


def fade_in(win, target=0.94, duration=200, slide=18, on_done=None):
    """Fade from transparent to `target` while sliding up a few pixels."""
    win.update_idletasks()
    try:
        x, y = win.winfo_x(), win.winfo_y()
    except tk.TclError:
        x = y = 0
    steps = max(1, duration // 16)
    _set_alpha(win, 0.0)

    def step(i=0):
        t = i / steps
        ease = 1 - (1 - t) ** 3  # ease-out cubic
        _set_alpha(win, target * ease)
        try:
            win.geometry(f"+{x}+{int(y + slide * (1 - ease))}")
        except tk.TclError:
            pass
        if i < steps:
            win.after(16, lambda: step(i + 1))
        elif on_done:
            on_done()

    step()


def fade_out(win, duration=160, slide=14, on_done=None):
    win.update_idletasks()
    try:
        x, y = win.winfo_x(), win.winfo_y()
        start = float(win.attributes("-alpha"))
    except (tk.TclError, ValueError):
        start, x, y = 0.94, 0, 0
    steps = max(1, duration // 16)

    def step(i=0):
        t = i / steps
        ease = t ** 2
        _set_alpha(win, start * (1 - ease))
        try:
            win.geometry(f"+{x}+{int(y + slide * ease)}")
        except tk.TclError:
            pass
        if i < steps:
            win.after(16, lambda: step(i + 1))
        elif on_done:
            on_done()

    step()


def make_draggable(win, handle):
    """Let a borderless `win` be dragged by clicking `handle`."""
    state = {"x": 0, "y": 0}

    def press(e):
        state["x"], state["y"] = e.x_root - win.winfo_x(), e.y_root - win.winfo_y()

    def drag(e):
        win.geometry(f"+{e.x_root - state['x']}+{e.y_root - state['y']}")

    handle.bind("<Button-1>", press)
    handle.bind("<B1-Motion>", drag)
