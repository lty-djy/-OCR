from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


DEFAULT_CAPTURE_SHORTCUT = QKeySequence("Ctrl+Shift+A")


class ShortcutDialog(QDialog):
    def __init__(self, current: QKeySequence, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置截图快捷键")
        self.setModal(True)
        self.setMinimumWidth(390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        layout.addWidget(QLabel("请直接按下新的截图识别快捷键："))
        self.sequence_edit = QKeySequenceEdit(current)
        self.sequence_edit.setMaximumSequenceLength(1)
        self.sequence_edit.setClearButtonEnabled(True)
        layout.addWidget(self.sequence_edit)
        hint = QLabel("支持 Ctrl、Alt、Shift、Win 与字母、数字或 F1-F24 组合。")
        hint.setStyleSheet("color: #66706b;")
        layout.addWidget(hint)

        actions = QHBoxLayout()
        default_button = QPushButton("恢复默认")
        default_button.clicked.connect(
            lambda: self.sequence_edit.setKeySequence(DEFAULT_CAPTURE_SHORTCUT)
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        actions.addWidget(default_button)
        actions.addStretch(1)
        actions.addWidget(buttons)
        layout.addLayout(actions)

    def selected_sequence(self) -> QKeySequence:
        return self.sequence_edit.keySequence()

