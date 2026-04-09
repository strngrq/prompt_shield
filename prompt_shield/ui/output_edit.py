from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QAction
from PySide6.QtWidgets import QTextEdit, QToolTip, QMenu

# Custom property IDs stored on QTextCharFormat
PROP_PLACEHOLDER = 0x100001
PROP_ORIGINAL = 0x100002
PROP_CATEGORY = 0x100003


def _char_format_at(doc, pos: int) -> QTextCharFormat:
    """Return the QTextCharFormat of the character at `pos` in the document."""
    c = QTextCursor(doc)
    c.setPosition(pos)
    c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
    return c.charFormat()


class OutputEdit(QTextEdit):
    """Read-only QTextEdit with hover tooltips and context-menu actions for placeholders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMouseTracking(True)

        self._db = None  # set externally

    def set_db(self, db):
        self._db = db

    # ── tooltip on hover ──────────────────────────────────

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        cursor = self.cursorForPosition(pos)
        fmt = cursor.charFormat()
        original = fmt.property(PROP_ORIGINAL)
        if original:
            QToolTip.showText(event.globalPosition().toPoint(), str(original), self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    # ── context menu ──────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        pos = event.pos()
        cursor = self.cursorForPosition(pos)
        fmt = cursor.charFormat()
        placeholder = fmt.property(PROP_PLACEHOLDER)
        original = fmt.property(PROP_ORIGINAL)

        # Check if user has a selection
        sel_cursor = self.textCursor()
        has_selection = sel_cursor.hasSelection()

        if placeholder and original:
            # Clicked on a placeholder — offer Unmask, Block, Allow
            unmask_action = QAction("Unmask (show original)", menu)
            unmask_action.triggered.connect(lambda: self._unmask_placeholder(cursor))
            menu.addAction(unmask_action)

            menu.addSeparator()

            block_action = QAction(f'Block "{original}"', menu)
            block_action.triggered.connect(lambda: self._block_text(str(original)))
            menu.addAction(block_action)

            allow_action = QAction(f'Allow "{original}"', menu)
            allow_action.triggered.connect(lambda: self._allow_text(str(original)))
            menu.addAction(allow_action)

        elif has_selection:
            selected_text = sel_cursor.selectedText().strip()
            if selected_text:
                mask_action = QAction("Mask selection", menu)
                mask_action.triggered.connect(lambda: self._mask_selection(sel_cursor))
                menu.addAction(mask_action)

                menu.addSeparator()

                block_action = QAction(f'Block "{selected_text}"', menu)
                block_action.triggered.connect(lambda: self._block_text_and_mask(selected_text, sel_cursor))
                menu.addAction(block_action)

                allow_action = QAction(f'Allow "{selected_text}"', menu)
                allow_action.triggered.connect(lambda: self._allow_text(selected_text))
                menu.addAction(allow_action)

        if menu.actions():
            menu.exec(event.globalPos())

    # ── actions ───────────────────────────────────────────

    def _unmask_placeholder(self, cursor: QTextCursor):
        """Replace a placeholder span with the original text (in this output only)."""
        fmt = cursor.charFormat()
        original = fmt.property(PROP_ORIGINAL)
        if not original:
            return

        # Select the whole placeholder token
        self._select_formatted_run(cursor)
        if not cursor.hasSelection():
            return

        # Replace with original text in default format
        default_fmt = QTextCharFormat()
        self.setReadOnly(False)
        cursor.insertText(str(original), default_fmt)
        self.setReadOnly(True)

    def _mask_selection(self, cursor: QTextCursor):
        """Replace selected clear text with a new placeholder (strips spaces)."""
        if not self._db:
            return
        selected = cursor.selectedText()
        stripped = selected.strip()
        if not stripped:
            return

        # Adjust selection to exclude leading/trailing spaces
        leading = len(selected) - len(selected.lstrip())
        trailing = len(selected) - len(selected.rstrip())
        start = cursor.selectionStart() + leading
        end = cursor.selectionEnd() - trailing
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

        placeholder = self._db.create_mapping(stripped, "INFO")
        fmt = self._placeholder_format(placeholder, stripped, "INFO")

        self.setReadOnly(False)
        cursor.insertText(placeholder, fmt)
        self.setReadOnly(True)

    def _block_text_and_mask(self, text: str, cursor: QTextCursor):
        """Add to block list AND immediately mask ALL occurrences in the output."""
        if not self._db:
            return
        stripped = text.strip()
        if not stripped:
            return
        self._db.add_block(stripped)

        placeholder = self._db.create_mapping(stripped, "BLOCKED")
        fmt = self._placeholder_format(placeholder, stripped, "BLOCKED")

        self._replace_all_plain_occurrences(stripped, placeholder, fmt)

    def _block_text(self, text: str):
        """Block from placeholder context menu — add to block list (already masked)."""
        if self._db:
            self._db.add_block(text)

    def _allow_text(self, text: str):
        if self._db:
            self._db.add_allow(text)

    def _replace_all_plain_occurrences(self, search_text: str, placeholder: str, fmt: QTextCharFormat):
        """Find and replace ALL plain-text (non-placeholder) occurrences of search_text."""
        doc = self.document()
        self.setReadOnly(False)

        # Search from the end to preserve positions
        full_text = self.toPlainText()
        search_lower = search_text.lower()

        # Collect positions of matches that are NOT already placeholders
        matches = []
        start = 0
        while True:
            idx = full_text.lower().find(search_lower, start)
            if idx == -1:
                break
            # Check if this span is already a placeholder
            char_fmt = _char_format_at(doc, idx)
            if not char_fmt.property(PROP_PLACEHOLDER):
                matches.append((idx, idx + len(search_text)))
            start = idx + 1

        # Replace from end to start to preserve earlier positions
        for m_start, m_end in reversed(matches):
            cursor = QTextCursor(doc)
            cursor.setPosition(m_start)
            cursor.setPosition(m_end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(placeholder, fmt)

        self.setReadOnly(True)

    # ── helpers ───────────────────────────────────────────

    def _select_formatted_run(self, cursor: QTextCursor):
        """Select the full contiguous run of chars sharing the same PROP_PLACEHOLDER."""
        placeholder = cursor.charFormat().property(PROP_PLACEHOLDER)
        if not placeholder:
            return

        doc = self.document()
        pos = cursor.position()
        max_pos = doc.characterCount() - 1  # last valid char index

        # cursor.charFormat() returns format of char BEFORE cursor position,
        # so the character we're "on" is at (pos - 1). But we need to handle
        # the case where pos == 0 as well.
        # Find a starting char index that definitely has our placeholder.
        # charFormat() at cursor position P describes char at P-1.
        anchor = max(pos - 1, 0)
        if _char_format_at(doc, anchor).property(PROP_PLACEHOLDER) != placeholder:
            # Try pos itself
            if pos < max_pos and _char_format_at(doc, pos).property(PROP_PLACEHOLDER) == placeholder:
                anchor = pos
            else:
                return

        # Scan left
        start = anchor
        while start > 0:
            if _char_format_at(doc, start - 1).property(PROP_PLACEHOLDER) != placeholder:
                break
            start -= 1

        # Scan right
        end = anchor + 1
        while end < max_pos:
            if _char_format_at(doc, end).property(PROP_PLACEHOLDER) != placeholder:
                break
            end += 1

        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

    @staticmethod
    def _placeholder_format(placeholder: str, original: str, category: str) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setBackground(QColor("#FFD966"))
        fmt.setForeground(QColor("#333333"))
        fmt.setProperty(PROP_PLACEHOLDER, placeholder)
        fmt.setProperty(PROP_ORIGINAL, original)
        fmt.setProperty(PROP_CATEGORY, category)
        fmt.setToolTip(original)
        return fmt
