"""
Window Manager: Finds and brings MCGG Game Window to front
Uses ctypes Win32 API to avoid pywintypes EnumWindows callback issues
"""
import ctypes
from ctypes import wintypes
import time
from typing import Optional, Tuple

user32 = ctypes.windll.user32

class GameWindowManager:
    def __init__(self, title_substring: str = "MagicChess"):
        self.title_substring = title_substring

    def find_game_hwnd(self) -> Optional[int]:
        """Finds window handle matching title substring."""
        found_hwnd = None
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def enum_windows_proc(hwnd, lParam):
            nonlocal found_hwnd
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    if self.title_substring.lower() in buff.value.lower():
                        found_hwnd = hwnd
                        return False  # Stop enumeration
            return True

        user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
        return found_hwnd

    def focus_game_window(self) -> bool:
        """Brings MCGG window to absolute foreground so terminal never blocks clicks."""
        hwnd = self.find_game_hwnd()
        if not hwnd:
            return False

        # SW_RESTORE = 9
        user32.ShowWindow(hwnd, 9)
        time.sleep(0.05)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)
        return True
