from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QTextEdit,
    QPushButton,
    QLabel,
    QSplitter,
    QApplication,
    QMessageBox,
)

from prompt_shield.core.database import Database
from prompt_shield.core.deanonymizer import deanonymize


class DeanonymizeTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        # ── input ──
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.addWidget(QLabel("Anonymized text (e.g. LLM response):"))
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("Paste anonymized text here...")
        input_layout.addWidget(self.input_edit)
        splitter.addWidget(input_container)

        # ── buttons ──
        btn_layout = QHBoxLayout()
        self.proceed_btn = QPushButton("Proceed")
        self.proceed_btn.clicked.connect(self._on_proceed)
        btn_layout.addStretch()
        btn_layout.addWidget(self.proceed_btn)
        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.clicked.connect(self._on_copy)
        btn_layout.addWidget(self.copy_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # ── output ──
        output_container = QWidget()
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(QLabel("Restored text:"))
        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        output_layout.addWidget(self.output_edit)
        splitter.addWidget(output_container)

    def _on_proceed(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        try:
            restored = deanonymize(text, self.db)
        except Exception as e:
            QMessageBox.critical(self, "De-anonymization Error", str(e))
            return
        self.output_edit.setPlainText(restored)

    def _on_copy(self):
        text = self.output_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
