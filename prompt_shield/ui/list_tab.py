from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QHeaderView,
    QAbstractItemView,
)

from prompt_shield.core.database import Database

# Column indices
COL_ID = 0
COL_TEXT = 1
COL_PREFIX = 2
COL_CASE = 3
COL_DATE = 4


class ListTab(QWidget):
    """Generic list management tab — used for both Block List and Allow List."""

    def __init__(self, db: Database, list_type: str):
        super().__init__()
        self.db = db
        self.list_type = list_type
        self._refreshing = False

        layout = QVBoxLayout(self)

        # ── filter ──
        filter_layout = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter...")
        self.filter_edit.textChanged.connect(self._on_filter)
        filter_layout.addWidget(self.filter_edit)
        layout.addLayout(filter_layout)

        # ── table ──
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["ID", "Text", "Prefix match", "Case sensitive", "Date added"])

        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(COL_TEXT)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnHidden(COL_ID, True)
        layout.addWidget(self.table)

        # Connect model changes for inline editing
        self.model.itemChanged.connect(self._on_item_changed)

        # ── add form ──
        add_layout = QHBoxLayout()
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Text to add...")
        add_layout.addWidget(self.text_input)

        self.prefix_cb = QCheckBox("Prefix match")
        add_layout.addWidget(self.prefix_cb)

        self.case_cb = QCheckBox("Case sensitive")
        add_layout.addWidget(self.case_cb)

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._on_add)
        add_layout.addWidget(self.add_btn)

        self.delete_btn = QPushButton("Delete selected")
        self.delete_btn.clicked.connect(self._on_delete)
        add_layout.addWidget(self.delete_btn)

        layout.addLayout(add_layout)

        self._refresh()

    def _refresh(self):
        self._refreshing = True
        self.model.removeRows(0, self.model.rowCount())
        rows = self.db.all_blocks() if self.list_type == "block" else self.db.all_allows()
        for row in rows:
            id_item = QStandardItem(str(row["id"]))
            id_item.setEditable(False)

            text_item = QStandardItem(row["text"])
            text_item.setEditable(True)

            prefix_item = QStandardItem()
            prefix_item.setCheckable(True)
            prefix_item.setCheckState(Qt.CheckState.Checked if row["prefix_match"] else Qt.CheckState.Unchecked)
            prefix_item.setEditable(False)

            case_item = QStandardItem()
            case_item.setCheckable(True)
            case_item.setCheckState(Qt.CheckState.Checked if row["case_sensitive"] else Qt.CheckState.Unchecked)
            case_item.setEditable(False)

            date_item = QStandardItem(row["added_at"])
            date_item.setEditable(False)

            self.model.appendRow([id_item, text_item, prefix_item, case_item, date_item])

        self.table.resizeColumnsToContents()
        self._refreshing = False

    def _on_item_changed(self, item: QStandardItem):
        """Handle inline edits — save changes to DB immediately."""
        if self._refreshing:
            return

        row = item.row()
        row_id = int(self.model.item(row, COL_ID).text())
        text = self.model.item(row, COL_TEXT).text().strip()
        prefix = self.model.item(row, COL_PREFIX).checkState() == Qt.CheckState.Checked
        case = self.model.item(row, COL_CASE).checkState() == Qt.CheckState.Checked

        if not text:
            self._refresh()
            return

        if self.list_type == "block":
            self.db.update_block(row_id, text, prefix, case)
        else:
            self.db.update_allow(row_id, text, prefix, case)

    def _on_add(self):
        text = self.text_input.text().strip()
        if not text:
            return
        prefix = self.prefix_cb.isChecked()
        case = self.case_cb.isChecked()

        if self.list_type == "block":
            self.db.add_block(text, prefix_match=prefix, case_sensitive=case)
        else:
            self.db.add_allow(text, prefix_match=prefix, case_sensitive=case)

        self.text_input.clear()
        self.prefix_cb.setChecked(False)
        self.case_cb.setChecked(False)
        self._refresh()

    def _on_delete(self):
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return

        ids_to_delete = []
        for idx in indexes:
            source_idx = self.proxy.mapToSource(idx)
            row_id = int(self.model.item(source_idx.row(), COL_ID).text())
            ids_to_delete.append(row_id)

        for row_id in ids_to_delete:
            if self.list_type == "block":
                self.db.remove_block(row_id)
            else:
                self.db.remove_allow(row_id)

        self._refresh()

    def _on_filter(self, text: str):
        self.proxy.setFilterFixedString(text)
