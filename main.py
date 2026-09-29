from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from inksnip_ocr.main_window import MainWindow


def resource_path(relative_path: str) -> Path:
    """同时兼容源码运行和以后 PyInstaller 打包后的资源路径。"""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / relative_path


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "InkSnip.OfflineOCR"
        )
    except Exception:
        pass


def run_self_test(device_key: str) -> int:
    """供发布流程调用：直接从打包后的 EXE 验证模型和推理后端。"""
    import numpy as np

    from inksnip_ocr.ocr_engine import OcrWorker

    image = np.full((96, 320, 3), 255, dtype=np.uint8)
    OcrWorker()._run(image, device_key)
    return 0


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        return run_self_test(sys.argv[2])

    QCoreApplication.setApplicationName("墨捕 OCR")
    QCoreApplication.setOrganizationName("InkSnip")
    set_windows_app_id()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # Qt 窗口运行时使用 PNG 可避免部分 Windows 环境不刷新 ICO 标题栏图标；
    # 多尺寸 ICO 保留给快捷方式和以后打包 EXE 使用。
    icon = QIcon(str(resource_path("assets/app-icon.png")))
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
