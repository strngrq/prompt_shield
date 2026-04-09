from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QLabel,
)

from prompt_shield.core.anonymizer import AnonymizationEngine
from prompt_shield.ui.anonymize_tab import AnonymizeTab
from prompt_shield.ui.deanonymize_tab import DeanonymizeTab
from prompt_shield.ui.list_tab import ListTab
from prompt_shield.ui.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self, db, config):
        super().__init__()
        self.db = db
        self.config = config

        self.setWindowTitle("PromptShield")
        self.resize(900, 640)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.engine = AnonymizationEngine(db)

        self.anonymize_tab = AnonymizeTab(self.engine, config, db=db)
        self.tabs.addTab(self.anonymize_tab, "Anonymize")
        self.deanonymize_tab = DeanonymizeTab(db)
        self.tabs.addTab(self.deanonymize_tab, "De-anonymize")
        self.block_list_tab = ListTab(db, "block")
        self.tabs.addTab(self.block_list_tab, "Block List")
        self.allow_list_tab = ListTab(db, "allow")
        self.tabs.addTab(self.allow_list_tab, "Allow List")
        self.settings_tab = SettingsTab(config)
        self.tabs.addTab(self.settings_tab, "Settings")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.anonymize_tab.refresh_languages()

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        if isinstance(widget, ListTab):
            widget._refresh()
        elif isinstance(widget, AnonymizeTab):
            widget.refresh_languages()
