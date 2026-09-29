from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


def _enum_value(value) -> int:
    return int(getattr(value, "value", value))


def sequence_to_windows_hotkey(sequence: QKeySequence) -> tuple[int, int]:
    """把单段 Qt 快捷键转换为 RegisterHotKey 的 modifiers 和 virtual key。"""
    if sequence.isEmpty() or sequence.count() != 1:
        raise ValueError("请输入一个完整的单段快捷键")

    combination = sequence[0]
    key = _enum_value(combination.key())
    qt_modifiers = combination.keyboardModifiers()

    modifiers = MOD_NOREPEAT
    if qt_modifiers & Qt.KeyboardModifier.AltModifier:
        modifiers |= MOD_ALT
    if qt_modifiers & Qt.KeyboardModifier.ControlModifier:
        modifiers |= MOD_CONTROL
    if qt_modifiers & Qt.KeyboardModifier.ShiftModifier:
        modifiers |= MOD_SHIFT
    if qt_modifiers & Qt.KeyboardModifier.MetaModifier:
        modifiers |= MOD_WIN

    if ord("A") <= key <= ord("Z") or ord("0") <= key <= ord("9"):
        virtual_key = key
    elif _enum_value(Qt.Key.Key_F1) <= key <= _enum_value(Qt.Key.Key_F24):
        virtual_key = 0x70 + key - _enum_value(Qt.Key.Key_F1)
    else:
        key_map = {
            _enum_value(Qt.Key.Key_Space): 0x20,
            _enum_value(Qt.Key.Key_Tab): 0x09,
            _enum_value(Qt.Key.Key_Backspace): 0x08,
            _enum_value(Qt.Key.Key_Return): 0x0D,
            _enum_value(Qt.Key.Key_Enter): 0x0D,
            _enum_value(Qt.Key.Key_Escape): 0x1B,
            _enum_value(Qt.Key.Key_Insert): 0x2D,
            _enum_value(Qt.Key.Key_Delete): 0x2E,
            _enum_value(Qt.Key.Key_Home): 0x24,
            _enum_value(Qt.Key.Key_End): 0x23,
            _enum_value(Qt.Key.Key_PageUp): 0x21,
            _enum_value(Qt.Key.Key_PageDown): 0x22,
            _enum_value(Qt.Key.Key_Left): 0x25,
            _enum_value(Qt.Key.Key_Up): 0x26,
            _enum_value(Qt.Key.Key_Right): 0x27,
            _enum_value(Qt.Key.Key_Down): 0x28,
            _enum_value(Qt.Key.Key_Print): 0x2C,
        }
        virtual_key = key_map.get(key, 0)

    if virtual_key == 0:
        raise ValueError("该按键暂不支持，请使用字母、数字、F1-F24 或常用功能键")
    return modifiers, virtual_key


class GlobalHotkey:
    """Windows RegisterHotKey 的小型生命周期封装。"""

    def __init__(self, window_handle: int, hotkey_id: int = 0x4D4F) -> None:
        self.window_handle = int(window_handle)
        self.hotkey_id = hotkey_id
        self.registered = False
        self.sequence = QKeySequence()
        self._user32 = None

        if sys.platform == "win32":
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._user32.RegisterHotKey.argtypes = [
                wintypes.HWND,
                ctypes.c_int,
                wintypes.UINT,
                wintypes.UINT,
            ]
            self._user32.RegisterHotKey.restype = wintypes.BOOL
            self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self._user32.UnregisterHotKey.restype = wintypes.BOOL

    @property
    def supported(self) -> bool:
        return self._user32 is not None

    def register(self, sequence: QKeySequence) -> tuple[bool, str]:
        self.unregister()
        if not self.supported:
            return False, "当前系统不支持 Windows 全局快捷键"

        try:
            modifiers, virtual_key = sequence_to_windows_hotkey(sequence)
        except ValueError as exc:
            return False, str(exc)

        ctypes.set_last_error(0)
        success = bool(
            self._user32.RegisterHotKey(
                self.window_handle,
                self.hotkey_id,
                modifiers,
                virtual_key,
            )
        )
        if not success:
            error_code = ctypes.get_last_error()
            if error_code == 1409:
                return False, "该快捷键已被其他程序占用"
            detail = ctypes.FormatError(error_code).strip() if error_code else "未知错误"
            return False, f"注册全局快捷键失败：{detail}"

        self.registered = True
        self.sequence = QKeySequence(sequence)
        return True, ""

    def unregister(self) -> None:
        if self.registered and self._user32 is not None:
            self._user32.UnregisterHotKey(self.window_handle, self.hotkey_id)
        self.registered = False

    def matches_native_message(self, message) -> bool:
        if not self.registered or sys.platform != "win32":
            return False
        native_message = wintypes.MSG.from_address(int(message))
        return (
            native_message.message == WM_HOTKEY
            and int(native_message.wParam) == self.hotkey_id
        )

