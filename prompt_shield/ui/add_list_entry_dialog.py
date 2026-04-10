"""Dialog for adding an entry to the block or allow list.

Shows lemmatization options for Russian words and a live preview of
matched word forms.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QGroupBox,
)

from prompt_shield.core.lang_morph import (
    is_russian_word,
    lemmatize,
    enumerate_forms,
    LemmatizeResult,
)


class AddListEntryDialog(QDialog):
    """Modal dialog that returns ``{text, prefix_match, case_sensitive}`` or ``None``."""

    def __init__(
        self,
        text: str,
        list_type: str = "block",
        source: str = "manual",
        parent=None,
    ):
        super().__init__(parent)
        self._original_text = text
        self._list_type = list_type
        self._source = source
        self._lemma_result: LemmatizeResult | None = None
        self._result: dict | None = None

        title = "Add to block list" if list_type == "block" else "Add to allow list"
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        # ── text field ──
        layout.addWidget(QLabel("Text:"))
        self._text_edit = QLineEdit(text)
        self._text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._text_edit)

        # ── lemma group (hidden for non-Russian) ──
        self._lemma_group = QGroupBox("Lemmatization")
        lemma_layout = QVBoxLayout(self._lemma_group)

        self._entered_label = QLabel()
        lemma_layout.addWidget(self._entered_label)

        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel("Save as:"))
        self._lemma_combo = QComboBox()
        self._lemma_combo.currentIndexChanged.connect(self._update_preview)
        combo_row.addWidget(self._lemma_combo, 1)
        lemma_layout.addLayout(combo_row)

        layout.addWidget(self._lemma_group)

        # ── checkboxes ──
        self._prefix_cb = QCheckBox("Match all word forms (recommended for names and brands)")
        self._prefix_cb.setChecked(source == "selection")
        self._prefix_cb.toggled.connect(self._update_preview)
        layout.addWidget(self._prefix_cb)

        self._case_cb = QCheckBox("Case sensitive")
        layout.addWidget(self._case_cb)

        # ── preview ──
        self._preview_label = QLabel()
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(
            "QLabel { color: #555; font-style: italic; padding: 4px; }"
        )
        layout.addWidget(self._preview_label)

        # ── buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        add_btn = QPushButton("Add")
        add_btn.setDefault(True)
        add_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(add_btn)

        layout.addLayout(btn_layout)

        self._rebuild_lemma_ui(text)

    # ── public API ────────────────────────────────────────

    def run(self) -> dict | None:
        self.exec()
        return self._result

    # ── slots ─────────────────────────────────────────────

    def _on_text_changed(self, text: str):
        self._rebuild_lemma_ui(text.strip())

    def _on_accept(self):
        text = self._effective_text()
        if not text:
            return
        self._result = {
            "text": text,
            "prefix_match": self._prefix_cb.isChecked(),
            "case_sensitive": self._case_cb.isChecked(),
        }
        self.accept()

    # ── internal ──────────────────────────────────────────

    def _effective_text(self) -> str:
        """Return the text that will be saved (lemma or as-typed)."""
        if self._lemma_group.isVisible() and self._lemma_combo.count() > 0:
            return self._lemma_combo.currentData() or self._text_edit.text().strip()
        return self._text_edit.text().strip()

    def _rebuild_lemma_ui(self, text: str):
        if not text or not is_russian_word(text):
            self._lemma_group.hide()
            self._lemma_result = None
            self._update_preview()
            return

        self._lemma_result = lemmatize(text)
        lr = self._lemma_result

        self._entered_label.setText(f"Entered: <b>{text}</b>")

        self._lemma_combo.blockSignals(True)
        self._lemma_combo.clear()

        if lr.primary and lr.primary != text.lower():
            self._lemma_combo.addItem(f"{lr.primary}  (lemma)", lr.primary)

        for alt in lr.alternatives:
            if alt != text.lower():
                self._lemma_combo.addItem(f"{alt}  (alt lemma)", alt)

        self._lemma_combo.addItem(f"{text}  (as typed)", text)
        self._lemma_combo.blockSignals(False)

        self._lemma_group.show()
        self._update_preview()

    def _update_preview(self):
        text = self._effective_text()
        if not text:
            self._preview_label.setText("")
            return

        if self._prefix_cb.isChecked() and is_russian_word(text):
            forms = enumerate_forms(text, limit=15)
            if forms:
                joined = ", ".join(forms)
                self._preview_label.setText(f"This will also catch: {joined}")
            else:
                self._preview_label.setText(
                    f'Prefix match enabled for "{text}"'
                )
        elif self._prefix_cb.isChecked():
            self._preview_label.setText(
                f'Prefix match: any word starting with "{text}"'
            )
        else:
            self._preview_label.setText(f'Only exact matches of: "{text}"')
