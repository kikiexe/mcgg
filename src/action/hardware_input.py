import ctypes
import time

# DPI Awareness Initialization: Mencegah Windows Display Scaling (125%, 150%) menggeser koordinat klik fisik
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32

# Mouse flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

def win32_click(x, y):
    """
    Kirim event hardware mouse murni via mouse_event Windows API.
    100% kompatibel dengan game Unity DirectX Fullscreen/Borderless.
    """
    # Normalisasi ke koordinat 0 - 65535 (Windows Absolute Coords)
    abs_x = int(x * 65535 / 1920)
    abs_y = int(y * 65535 / 1080)

    # 1. Gerakkan kursor fisik
    user32.SetCursorPos(x, y)
    user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, abs_x, abs_y, 0, 0)
    time.sleep(0.08)

    # 2. Tekan dan tahan (Mouse Down)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.12)  # Hold time penting untuk game Unity

    # 3. Lepaskan (Mouse Up)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.1)
    print(f"[WIN32] Hardware Click dieksekusi di ({x}, {y})")

def win32_drag(x1, y1, x2, y2):
    """
    Drag and drop fisik dengan mouse_event yang menembus collider Unity.
    Menyuntikkan event MOUSEEVENTF_MOVE dan koordinat absolut ke DirectInput
    di setiap step interpolasi agar raycaster engine mengenali pergerakan drag.
    """
    abs_x1 = int(x1 * 65535 / 1920)
    abs_y1 = int(y1 * 65535 / 1080)
    user32.SetCursorPos(x1, y1)
    user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, abs_x1, abs_y1, 0, 0)
    time.sleep(0.08)

    # 1. Tekan tombol mouse kiri dan tahan untuk mengangkat pion
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.2)

    # 2. Interpolasi pergerakan dengan mouse_event absolut
    steps = 30
    for i in range(1, steps + 1):
        cx = int(x1 + (x2 - x1) * (i / steps))
        cy = int(y1 + (y2 - y1) * (i / steps))
        abs_cx = int(cx * 65535 / 1920)
        abs_cy = int(cy * 65535 / 1080)
        user32.SetCursorPos(cx, cy)
        user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, abs_cx, abs_cy, 0, 0)
        time.sleep(0.012)

    # 3. Tahan sejenak di koordinat tujuan agar snapping board Unity aktif
    time.sleep(0.2)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.1)
    print(f"[WIN32] Hardware Drag dari ({x1}, {y1}) ke ({x2}, {y2})")

def win32_press_key(vk_code):
    """Kirim penekanan tombol keyboard fisik."""
    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.08)
    user32.keybd_event(vk_code, 0, 0x0002, 0)  # KEYEVENTF_KEYUP
    time.sleep(0.1)
