from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


class CaptureOverlay(QWidget):
    """在鼠标所在屏幕上提供截图框选。"""

    captured = Signal(object)
    canceled = Signal()

    def __init__(self) -> None:
        super().__init__()
        cursor_position = self.cursor().pos()
        self._screen = QApplication.screenAt(cursor_position)
        if self._screen is None:
            self._screen = QApplication.primaryScreen()
        if self._screen is None:
            raise RuntimeError("没有检测到可用屏幕")

        # 必须在遮罩窗口显示前抓屏，否则会把遮罩本身截进去。
        self._desktop = self._screen.grabWindow(0)
        self._origin: QPoint | None = None
        self._current: QPoint | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(self._screen.geometry())

    def selection_rect(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized().intersected(self.rect())

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._desktop)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 105))

        selected = self.selection_rect()
        if selected.isValid() and not selected.isEmpty():
            painter.save()
            painter.setClipRect(selected)
            painter.drawPixmap(self.rect(), self._desktop)
            painter.restore()

            painter.setPen(QPen(QColor("#38b26d"), 2))
            painter.drawRect(selected.adjusted(0, 0, -1, -1))

            label = f"{selected.width()} × {selected.height()}"
            label_rect = QRect(selected.left(), max(0, selected.top() - 28), 120, 24)
            painter.fillRect(label_rect, QColor(20, 24, 28, 220))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                label_rect.adjusted(8, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter,
                label,
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        self._current = event.position().toPoint()
        selected = self.selection_rect()
        if selected.width() < 5 or selected.height() < 5:
            self._origin = None
            self._current = None
            self.update()
            return

        scale_x = self._desktop.width() / max(1, self.width())
        scale_y = self._desktop.height() / max(1, self.height())
        source_rect = QRect(
            round(selected.x() * scale_x),
            round(selected.y() * scale_y),
            max(1, round(selected.width() * scale_x)),
            max(1, round(selected.height() * scale_y)),
        ).intersected(self._desktop.rect())
        cropped = self._desktop.copy(source_rect)
        cropped.setDevicePixelRatio(self._desktop.devicePixelRatio())

        self.hide()
        self.captured.emit(cropped)
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def _cancel(self) -> None:
        self.hide()
        self.canceled.emit()
        self.close()

