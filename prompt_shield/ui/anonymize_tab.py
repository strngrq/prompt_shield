from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QLabel,
    QSplitter,
    QApplication,
    QComboBox,
    QMessageBox,
)

from prompt_shield.core.anonymizer import AnonymizationEngine, ReplacementInfo
from prompt_shield.core.config import Config
from prompt_shield.ui.output_edit import (
    OutputEdit,
    PROP_PLACEHOLDER,
    PROP_ORIGINAL,
    PROP_CATEGORY,
    ANONYMOUS_MASK,
)


class AnonymizeTab(QWidget):
    def __init__(self, engine: AnonymizationEngine, config: Config, db=None):
        super().__init__()
        self.engine = engine
        self.config = config
        self._replacements: list[ReplacementInfo] = []

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        # ── input pane ──
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.addWidget(QLabel("Input text:"))
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("Paste or type text here...")
        input_layout.addWidget(self.input_edit)
        splitter.addWidget(input_container)

        # ── buttons ──
        btn_layout = QHBoxLayout()

        self.lang_combo = QComboBox()
        self.lang_combo.setToolTip("Language of the input text")
        self.lang_combo.setMinimumWidth(120)
        btn_layout.addWidget(QLabel("Language:"))
        btn_layout.addWidget(self.lang_combo)

        self.proceed_btn = QPushButton("Proceed")
        self.proceed_btn.clicked.connect(self._on_proceed)
        btn_layout.addStretch()
        btn_layout.addWidget(self.proceed_btn)
        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.clicked.connect(self._on_copy)
        btn_layout.addWidget(self.copy_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # ── output pane ──
        output_container = QWidget()
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(QLabel("Anonymized output:"))
        self.output_edit = OutputEdit()
        self.output_edit.set_config(config)
        if db:
            self.output_edit.set_db(db)
        output_layout.addWidget(self.output_edit)
        splitter.addWidget(output_container)

    def refresh_languages(self):
        """Rebuild the language combo from config['active_languages']."""
        from prompt_shield.ui.settings_tab import AVAILABLE_LANGUAGES

        current = self.lang_combo.currentData()
        self.lang_combo.clear()

        for code in self.config["active_languages"]:
            info = AVAILABLE_LANGUAGES.get(code)
            if info:
                self.lang_combo.addItem(f"{info['name']} ({code})", code)

        if self.lang_combo.count() == 0:
            self.lang_combo.addItem("English (en)", "en")

        # Restore previous selection if still available
        if current:
            idx = self.lang_combo.findData(current)
            if idx >= 0:
                self.lang_combo.setCurrentIndex(idx)

    def _on_proceed(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        language = self.lang_combo.currentData() or "en"
        categories = self.config["enabled_categories"]
        threshold = self.config["sensitivity_threshold"]

        try:
            anonymized, replacements = self.engine.anonymize(
                text,
                language=language,
                categories=categories,
                threshold=threshold,
            )
        except Exception as e:
            QMessageBox.critical(self, "Anonymization Error", str(e))
            return

        self._replacements = replacements
        self._render_output(anonymized, replacements)

    def _render_output(self, text: str, replacements: list[ReplacementInfo]):
        """Render anonymized text with styled placeholder spans."""
        self.output_edit.clear()
        cursor = self.output_edit.textCursor()

        default_fmt = QTextCharFormat()

        sorted_repls = sorted(replacements, key=lambda r: r.start)
        repl_idx = 0
        pos = 0
        use_mask = bool(self.config.get("anonymous_mask"))

        while pos < len(text):
            if repl_idx < len(sorted_repls) and pos == sorted_repls[repl_idx].start:
                r = sorted_repls[repl_idx]
                fmt = OutputEdit._placeholder_format(r.placeholder, r.original_text, r.category)
                display = ANONYMOUS_MASK if use_mask else r.placeholder
                cursor.insertText(display, fmt)
                pos = r.end
                repl_idx += 1
            else:
                next_start = sorted_repls[repl_idx].start if repl_idx < len(sorted_repls) else len(text)
                cursor.insertText(text[pos:next_start], default_fmt)
                pos = next_start

        self.output_edit.setTextCursor(cursor)

    def _on_copy(self):
        text = self.output_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def get_replacements(self) -> list[ReplacementInfo]:
        return self._replacements
