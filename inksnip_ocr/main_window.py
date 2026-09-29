from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, Qt, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QFont,
    QImage,
    QImageReader,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from inksnip_ocr.capture_overlay import CaptureOverlay
from inksnip_ocr.global_hotkey import GlobalHotkey
from inksnip_ocr.ocr_engine import (
    OcrOutput,
    OcrRequest,
    OcrWorker,
    detect_available_devices,
    pixmap_to_rgb_array,
)
from inksnip_ocr.shortcut_dialog import DEFAULT_CAPTURE_SHORTCUT, ShortcutDialog


IMAGE_FILE_FILTER = (
    "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;所有文件 (*.*)"
)


def read_local_image(file_path: str) -> QImage:
    """读取本地图片并应用相机照片中的 EXIF 旋转信息。"""
    path = Path(file_path)
    if not path.is_file():
        raise ValueError("所选图片不存在或已被移动。")

    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        detail = reader.errorString() or "未知格式或图片已经损坏"
        raise ValueError(f"无法读取该图片：{detail}")
    return image


class MainWindow(QMainWindow):
    recognize_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("墨捕 OCR · 本地离线截图识别")
        self.resize(820, 560)
        self.setMinimumSize(620, 420)

        self._overlay: CaptureOverlay | None = None
        self._busy = False
        self._settings = QSettings()
        self._devices = detect_available_devices()
        self._capture_sequence = self._load_capture_sequence()

        self._build_ui()
        self._build_ocr_thread()
        self._apply_style()

        self._copy_shortcut = QShortcut(
            QKeySequence("Ctrl+Return"), self, activated=self.copy_result
        )
        self._global_hotkey = GlobalHotkey(int(self.winId()))
        QTimer.singleShot(0, self._register_initial_hotkey)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("墨捕 OCR")
        title.setObjectName("title")
        subtitle = QLabel("截图后在本机完成文字识别，不调用云端 OCR API")
        subtitle.setObjectName("subtitle")

        toolbar = QVBoxLayout()
        toolbar.setSpacing(8)
        action_row = QHBoxLayout()
        option_row = QHBoxLayout()
        self.capture_button = QPushButton()
        self.capture_button.setObjectName("primaryButton")
        self.capture_button.clicked.connect(self.start_capture)
        self._update_capture_button_text()

        self.image_button = QPushButton("图片识别…")
        self.image_button.setToolTip("选择本机图片并离线识别其中的文字")
        self.image_button.clicked.connect(self.select_image)

        shortcut_button = QPushButton("快捷键…")
        shortcut_button.setToolTip("修改系统级截图识别快捷键")
        shortcut_button.clicked.connect(self.configure_capture_shortcut)

        self.copy_button = QPushButton("复制文字")
        self.copy_button.clicked.connect(self.copy_result)
        clear_button = QPushButton("清空")
        clear_button.clicked.connect(self.clear_result)
        self.auto_copy = QCheckBox("识别后自动复制")
        self.auto_copy.setChecked(True)

        self.device_label = QLabel("推理设备")
        self.device_combo = QComboBox()
        for device in self._devices:
            self.device_combo.addItem(device.label, device.key)
        saved_device = str(self._settings.value("ocr/device", "cpu"))
        saved_index = self.device_combo.findData(saved_device)
        self.device_combo.setCurrentIndex(max(0, saved_index))
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)

        # CPU-only 电脑没有可切换项，隐藏设备控件，自动使用 CPU。
        has_gpu_choice = len(self._devices) > 1
        self.device_label.setVisible(has_gpu_choice)
        self.device_combo.setVisible(has_gpu_choice)

        action_row.addWidget(self.capture_button)
        action_row.addWidget(self.image_button)
        action_row.addWidget(shortcut_button)
        action_row.addWidget(self.copy_button)
        action_row.addWidget(clear_button)
        action_row.addStretch(1)
        option_row.addStretch(1)
        option_row.addWidget(self.device_label)
        option_row.addWidget(self.device_combo)
        option_row.addWidget(self.auto_copy)
        toolbar.addLayout(action_row)
        toolbar.addLayout(option_row)

        self.result_edit = QTextEdit()
        self.result_edit.setPlaceholderText("识别结果将显示在这里……")
        self.result_edit.setAcceptRichText(False)
        self.result_edit.setFont(QFont("Microsoft YaHei UI", 12))

        self.status_label = QLabel("就绪 · 点击“截图识别”后拖动鼠标框选，Esc 或右键取消")
        self.status_label.setObjectName("status")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(toolbar)
        layout.addWidget(self.result_edit, 1)
        layout.addWidget(self.status_label)
        self.setCentralWidget(root)

    def _build_ocr_thread(self) -> None:
        self._ocr_thread = QThread(self)
        self._ocr_worker = OcrWorker()
        self._ocr_worker.moveToThread(self._ocr_thread)
        self.recognize_requested.connect(self._ocr_worker.recognize)
        self._ocr_worker.completed.connect(self._on_ocr_completed)
        self._ocr_worker.failed.connect(self._on_ocr_failed)
        self._ocr_thread.start()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f5f7f6; color: #202624; }
            QLabel#title { font-size: 28px; font-weight: 700; color: #247a4b; }
            QLabel#subtitle { color: #66706b; font-size: 13px; }
            QLabel#status { color: #66706b; padding: 4px 2px; }
            QTextEdit {
                background: white; border: 1px solid #ccd5d0; border-radius: 8px;
                padding: 12px; selection-background-color: #4aa675;
            }
            QPushButton {
                background: white; border: 1px solid #bec9c3; border-radius: 6px;
                padding: 9px 14px; min-height: 18px;
            }
            QPushButton:hover { border-color: #38a469; background: #f0faf4; }
            QPushButton:disabled { color: #9aa39f; background: #ecefed; }
            QPushButton#primaryButton {
                color: white; background: #2f9e62; border-color: #2f9e62;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover { background: #278954; }
            QCheckBox { spacing: 7px; }
            QComboBox {
                background: white; border: 1px solid #bec9c3; border-radius: 6px;
                padding: 7px 10px; min-width: 130px;
            }
            """
        )

    def start_capture(self) -> None:
        if self._busy or self._overlay is not None:
            return
        self.status_label.setText("准备截图……")
        self.hide()
        QTimer.singleShot(180, self._show_capture_overlay)

    def select_image(self) -> None:
        if self._busy or self._overlay is not None:
            return

        start_directory = str(self._settings.value("image/last_directory", ""))
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "选择需要识别的图片",
            start_directory,
            IMAGE_FILE_FILTER,
        )
        if not file_path:
            return

        self._settings.setValue("image/last_directory", str(Path(file_path).parent))
        try:
            image = read_local_image(file_path)
        except ValueError as exc:
            self.status_label.setText("图片读取失败")
            QMessageBox.warning(self, "无法读取图片", str(exc))
            return

        self._recognize_pixmap(
            QPixmap.fromImage(image), source_label=f"图片“{Path(file_path).name}”"
        )

    def _load_capture_sequence(self) -> QKeySequence:
        saved = str(
            self._settings.value(
                "shortcut/capture",
                DEFAULT_CAPTURE_SHORTCUT.toString(QKeySequence.SequenceFormat.PortableText),
            )
        )
        sequence = QKeySequence.fromString(
            saved, QKeySequence.SequenceFormat.PortableText
        )
        return sequence if not sequence.isEmpty() else QKeySequence(DEFAULT_CAPTURE_SHORTCUT)

    def _shortcut_text(self) -> str:
        return self._capture_sequence.toString(QKeySequence.SequenceFormat.NativeText)

    def _update_capture_button_text(self) -> None:
        self.capture_button.setText(f"截图识别  {self._shortcut_text()}")

    def _register_initial_hotkey(self) -> None:
        success, message = self._global_hotkey.register(self._capture_sequence)
        if success:
            return
        self.status_label.setText(f"全局快捷键未启用：{message}；仍可点击按钮截图")

    def configure_capture_shortcut(self) -> None:
        old_sequence = QKeySequence(self._capture_sequence)
        self._global_hotkey.unregister()
        dialog = ShortcutDialog(old_sequence, self)
        if dialog.exec() != ShortcutDialog.DialogCode.Accepted:
            self._global_hotkey.register(old_sequence)
            return

        new_sequence = dialog.selected_sequence()
        if new_sequence.isEmpty():
            QMessageBox.warning(self, "快捷键无效", "快捷键不能为空。")
            self._global_hotkey.register(old_sequence)
            return
        if new_sequence.matches(QKeySequence("Ctrl+Return")) == QKeySequence.SequenceMatch.ExactMatch:
            QMessageBox.warning(self, "快捷键冲突", "Ctrl+Enter 已用于复制识别结果。")
            self._global_hotkey.register(old_sequence)
            return

        success, message = self._global_hotkey.register(new_sequence)
        if not success:
            QMessageBox.warning(self, "无法使用该快捷键", message)
            self._global_hotkey.register(old_sequence)
            return

        self._capture_sequence = QKeySequence(new_sequence)
        self._settings.setValue(
            "shortcut/capture",
            new_sequence.toString(QKeySequence.SequenceFormat.PortableText),
        )
        self._update_capture_button_text()
        self.status_label.setText(f"截图快捷键已修改为 {self._shortcut_text()}")

    def _show_capture_overlay(self) -> None:
        try:
            self._overlay = CaptureOverlay()
            self._overlay.captured.connect(self._on_captured)
            self._overlay.canceled.connect(self._on_capture_canceled)
            self._overlay.destroyed.connect(self._release_overlay)
            self._overlay.show()
            self._overlay.raise_()
            self._overlay.activateWindow()
            self._overlay.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        except Exception as exc:
            self.show()
            self.status_label.setText("截图启动失败")
            QMessageBox.critical(self, "截图失败", str(exc))

    def _release_overlay(self) -> None:
        self._overlay = None

    def _on_capture_canceled(self) -> None:
        self.show()
        self.activateWindow()
        self.status_label.setText("已取消截图")

    def _on_captured(self, pixmap: QPixmap) -> None:
        self._recognize_pixmap(pixmap, source_label="截图")

    def _recognize_pixmap(self, pixmap: QPixmap, source_label: str) -> None:
        self.show()
        self.activateWindow()
        self._set_busy(True)
        self.status_label.setText(f"正在加载本地模型并识别{source_label}，请稍候……")
        try:
            image = pixmap_to_rgb_array(pixmap)
            self.recognize_requested.emit(
                OcrRequest(image=image, device_key=self.current_device_key())
            )
        except Exception as exc:
            self._on_ocr_failed(f"{type(exc).__name__}: {exc}")

    def _on_ocr_completed(self, output: OcrOutput) -> None:
        self._set_busy(False)
        if output.fallback_message:
            cpu_index = self.device_combo.findData("cpu")
            self.device_combo.blockSignals(True)
            self.device_combo.setCurrentIndex(cpu_index)
            self.device_combo.blockSignals(False)
            self._settings.setValue("ocr/device", "cpu")
        self.result_edit.setPlainText(output.text)
        if not output.text:
            prefix = "GPU 不可用，已回退 CPU · " if output.fallback_message else ""
            self.status_label.setText(
                prefix + "未识别到文字，请扩大截图范围或换一处文字重试"
            )
            return

        if self.auto_copy.isChecked():
            QApplication.clipboard().setText(output.text)
        confidence = ""
        if output.average_confidence is not None:
            confidence = f" · 平均置信度 {output.average_confidence:.1%}"
        copied = " · 已复制" if self.auto_copy.isChecked() else ""
        elapsed = ""
        if output.elapsed_seconds is not None:
            elapsed = f" · {output.elapsed_seconds:.2f} 秒"
        fallback = " · GPU 不可用，已回退 CPU" if output.fallback_message else ""
        self.status_label.setText(
            f"识别完成 · {output.device_label}{elapsed} · "
            f"{output.line_count} 行{confidence}{copied}{fallback}"
        )

    def _on_ocr_failed(self, message: str) -> None:
        self._set_busy(False)
        self.status_label.setText("识别失败")
        QMessageBox.critical(
            self,
            "本地 OCR 识别失败",
            f"识别过程中发生错误：\n\n{message}",
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.capture_button.setDisabled(busy)
        self.image_button.setDisabled(busy)
        self.device_combo.setDisabled(busy)

    def current_device_key(self) -> str:
        return str(self.device_combo.currentData() or "cpu")

    def _on_device_changed(self) -> None:
        device_key = self.current_device_key()
        self._settings.setValue("ocr/device", device_key)
        self.status_label.setText(
            f"已选择 {self.device_combo.currentText()}，将在下一次识别时生效"
        )

    def copy_result(self) -> None:
        text = self.result_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status_label.setText("识别文字已复制到剪贴板")

    def clear_result(self) -> None:
        self.result_edit.clear()
        self.status_label.setText("已清空")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._overlay is not None:
            self._overlay.close()
        self._ocr_thread.quit()
        if not self._ocr_thread.wait(3000):
            event.ignore()
            QMessageBox.warning(self, "正在退出", "OCR 任务仍在结束，请稍后再次关闭。")
            return
        self._global_hotkey.unregister()
        event.accept()

    def nativeEvent(self, event_type, message):  # noqa: N802
        hotkey = getattr(self, "_global_hotkey", None)
        if hotkey is not None and hotkey.matches_native_message(message):
            QTimer.singleShot(0, self.start_capture)
            return True, 0
        return super().nativeEvent(event_type, message)
