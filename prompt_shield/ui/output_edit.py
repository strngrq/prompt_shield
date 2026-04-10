from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QAction
from PySide6.QtWidgets import QTextEdit, QToolTip, QMenu, QLabel, QVBoxLayout, QWidget

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


def _strip_whitespace_from_selection(cursor: QTextCursor) -> str | None:
    """Shrink cursor selection to exclude leading/trailing whitespace.

    Returns the stripped text, or None if nothing remains.
    """
    selected = cursor.selectedText()
    stripped = selected.strip()
    if not stripped:
        return None
    leading = len(selected) - len(selected.lstrip())
    trailing = len(selected) - len(selected.rstrip())
    start = cursor.selectionStart() + leading
    end = cursor.selectionEnd() - trailing
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    return stripped


class OutputEdit(QTextEdit):
    """Read-only QTextEdit with hover tooltips and context-menu actions for placeholders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMouseTracking(True)

        self._db = None

        self._hint_label = QLabel(
            "Hold Alt (⌥) for exact selection without snap-to-word", self
        )
        self._hint_label.setStyleSheet(
            "QLabel { background: #444; color: #eee; padding: 3px 8px;"
            " border-radius: 3px; font-size: 11px; }"
        )
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.hide()

    def set_db(self, db):
        self._db = db

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_hint()

    def _position_hint(self):
        lbl = self._hint_label
        lbl.adjustSize()
        x = (self.width() - lbl.width()) // 2
        y = self.height() - lbl.height() - 6
        lbl.move(x, y)

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

    # ── show/hide hint on selection change ─────────────────

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        cursor = self.textCursor()
        if cursor.hasSelection():
            alt_held = event.modifiers() & Qt.KeyboardModifier.AltModifier
            if not alt_held:
                self._normalize_selection_to_words(cursor)
                self.setTextCursor(cursor)
            self._hint_label.show()
            self._position_hint()
        else:
            self._hint_label.hide()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._hint_label.hide()

    # ── snap-to-word ──────────────────────────────────────

    def _normalize_selection_to_words(self, cursor: QTextCursor) -> str | None:
        """Expand a partial-word selection to full word boundaries.

        Uses Qt's StartOfWord / EndOfWord which follow ICU Unicode rules,
        so Cyrillic, CJK, umlauts etc. are handled correctly.
        Returns the stripped selected text, or None if empty.
        """
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        tmp = QTextCursor(cursor.document())
        tmp.setPosition(start)
        tmp.movePosition(QTextCursor.MoveOperation.StartOfWord)
        new_start = tmp.position()

        tmp.setPosition(end)
        tmp.movePosition(QTextCursor.MoveOperation.EndOfWord)
        new_end = tmp.position()

        cursor.setPosition(new_start)
        cursor.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)

        return _strip_whitespace_from_selection(cursor)

    # ── context menu ──────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        pos = event.pos()
        cursor = self.cursorForPosition(pos)
        fmt = cursor.charFormat()
        placeholder = fmt.property(PROP_PLACEHOLDER)
        original = fmt.property(PROP_ORIGINAL)

        sel_cursor = self.textCursor()
        has_selection = sel_cursor.hasSelection()

        if placeholder and original:
            unmask_action = QAction("Unmask (show original)", menu)
            unmask_action.triggered.connect(lambda: self._unmask_placeholder(cursor))
            menu.addAction(unmask_action)

            menu.addSeparator()

            block_action = QAction(f'Block "{original}"', menu)
            block_action.triggered.connect(lambda: self._block_text(str(original)))
            menu.addAction(block_action)

            _ph, _orig = str(placeholder), str(original)
            allow_action = QAction(f'Allow "{original}"', menu)
            allow_action.triggered.connect(
                lambda: self._allow_text(_orig, unmask_placeholder=_ph)
            )
            menu.addAction(allow_action)

        elif has_selection:
            selected_text = _strip_whitespace_from_selection(sel_cursor)

            if selected_text:
                mask_action = QAction("Mask selection", menu)
                mask_action.triggered.connect(lambda: self._mask_selection(sel_cursor))
                menu.addAction(mask_action)

                menu.addSeparator()

                block_action = QAction(f'Block "{selected_text}"', menu)
                block_action.triggered.connect(
                    lambda: self._block_text_and_mask(selected_text, sel_cursor)
                )
                menu.addAction(block_action)

                allow_action = QAction(f'Allow "{selected_text}"', menu)
                allow_action.triggered.connect(lambda: self._allow_text(selected_text))
                menu.addAction(allow_action)

        else:
            # No selection — snap to the word under the right-click position
            word_cursor = QTextCursor(cursor)
            word_cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            word_text = word_cursor.selectedText().strip()
            if word_text:
                self.setTextCursor(word_cursor)

                mask_action = QAction(f'Mask "{word_text}"', menu)
                mask_action.triggered.connect(lambda: self._mask_selection(word_cursor))
                menu.addAction(mask_action)

                menu.addSeparator()

                block_action = QAction(f'Block "{word_text}"', menu)
                block_action.triggered.connect(
                    lambda: self._block_text_and_mask(word_text, word_cursor)
                )
                menu.addAction(block_action)

                allow_action = QAction(f'Allow "{word_text}"', menu)
                allow_action.triggered.connect(lambda: self._allow_text(word_text))
                menu.addAction(allow_action)

        if menu.actions():
            self._hint_label.hide()
            menu.exec(event.globalPos())

    # ── actions ───────────────────────────────────────────

    def _unmask_placeholder(self, cursor: QTextCursor):
        """Replace a placeholder span with the original text (in this output only)."""
        fmt = cursor.charFormat()
        original = fmt.property(PROP_ORIGINAL)
        if not original:
            return

        self._select_formatted_run(cursor)
        if not cursor.hasSelection():
            return

        default_fmt = QTextCharFormat()
        self.setReadOnly(False)
        cursor.insertText(str(original), default_fmt)
        self.setReadOnly(True)

    def _mask_selection(self, cursor: QTextCursor):
        """Replace selected clear text with a new placeholder."""
        if not self._db:
            return

        stripped = _strip_whitespace_from_selection(cursor)
        if not stripped:
            return

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

        from prompt_shield.ui.add_list_entry_dialog import AddListEntryDialog

        dlg = AddListEntryDialog(
            text=stripped, list_type="block", source="selection", parent=self
        )
        result = dlg.run()
        if result is None:
            return

        self._db.add_block(
            result["text"],
            prefix_match=result["prefix_match"],
            case_sensitive=result["case_sensitive"],
        )

        placeholder = self._db.create_mapping(stripped, "BLOCKED")
        fmt = self._placeholder_format(placeholder, stripped, "BLOCKED")
        self._replace_all_plain_occurrences(stripped, placeholder, fmt)

    def _block_text(self, text: str):
        """Block from placeholder context menu — add to block list (already masked)."""
        if not self._db:
            return

        from prompt_shield.ui.add_list_entry_dialog import AddListEntryDialog

        dlg = AddListEntryDialog(
            text=text, list_type="block", source="selection", parent=self
        )
        result = dlg.run()
        if result is None:
            return

        self._db.add_block(
            result["text"],
            prefix_match=result["prefix_match"],
            case_sensitive=result["case_sensitive"],
        )

    def _allow_text(self, text: str, unmask_placeholder: str | None = None):
        if not self._db:
            return

        from prompt_shield.ui.add_list_entry_dialog import AddListEntryDialog

        dlg = AddListEntryDialog(
            text=text, list_type="allow", source="selection", parent=self
        )
        result = dlg.run()
        if result is None:
            return

        self._db.add_allow(
            result["text"],
            prefix_match=result["prefix_match"],
            case_sensitive=result["case_sensitive"],
        )

        if unmask_placeholder:
            self._unmask_all_occurrences(unmask_placeholder)

    def _unmask_all_occurrences(self, placeholder_name: str):
        """Replace every span tagged with *placeholder_name* with its original text."""
        doc = self.document()
        self.setReadOnly(False)
        default_fmt = QTextCharFormat()

        pos = 0
        max_pos = doc.characterCount() - 1
        while pos < max_pos:
            fmt = _char_format_at(doc, pos)
            if fmt.property(PROP_PLACEHOLDER) == placeholder_name:
                original = str(fmt.property(PROP_ORIGINAL) or "")
                cursor = QTextCursor(doc)
                cursor.setPosition(pos)
                # scan to end of this run
                end = pos + 1
                while end < max_pos:
                    if _char_format_at(doc, end).property(PROP_PLACEHOLDER) != placeholder_name:
                        break
                    end += 1
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(original, default_fmt)
                # after insertion, continue from pos + len(original)
                pos += len(original)
                max_pos = doc.characterCount() - 1
            else:
                pos += 1

        self.setReadOnly(True)

    def _replace_all_plain_occurrences(self, search_text: str, placeholder: str, fmt: QTextCharFormat):
        """Find and replace ALL plain-text (non-placeholder) occurrences of search_text."""
        doc = self.document()
        self.setReadOnly(False)

        full_text = self.toPlainText()
        search_lower = search_text.lower()

        matches = []
        start = 0
        while True:
            idx = full_text.lower().find(search_lower, start)
            if idx == -1:
                break
            char_fmt = _char_format_at(doc, idx)
            if not char_fmt.property(PROP_PLACEHOLDER):
                matches.append((idx, idx + len(search_text)))
            start = idx + 1

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
        max_pos = doc.characterCount() - 1

        anchor = max(pos - 1, 0)
        if _char_format_at(doc, anchor).property(PROP_PLACEHOLDER) != placeholder:
            if pos < max_pos and _char_format_at(doc, pos).property(PROP_PLACEHOLDER) == placeholder:
                anchor = pos
            else:
                return

        start = anchor
        while start > 0:
            if _char_format_at(doc, start - 1).property(PROP_PLACEHOLDER) != placeholder:
                break
            start -= 1

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
