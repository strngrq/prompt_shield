from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QCheckBox,
    QSlider,
    QDoubleSpinBox,
    QLabel,
    QScrollArea,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QProgressBar,
    QComboBox,
    QMessageBox,
)

from prompt_shield.core.config import Config

ALL_CATEGORIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",
    "ORGANIZATION",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "URL",
    "DATE_TIME",
]

AVAILABLE_LANGUAGES = {
    "en": {"name": "English", "models": {"sm": "en_core_web_sm", "lg": "en_core_web_lg"}},
    "ru": {"name": "Russian", "models": {"sm": "ru_core_news_sm", "lg": "ru_core_news_lg"}},
    "de": {"name": "German", "models": {"sm": "de_core_news_sm", "lg": "de_core_news_lg"}},
    "fr": {"name": "French", "models": {"sm": "fr_core_news_sm", "lg": "fr_core_news_lg"}},
    "es": {"name": "Spanish", "models": {"sm": "es_core_news_sm", "lg": "es_core_news_lg"}},
    "zh": {"name": "Chinese", "models": {"sm": "zh_core_web_sm", "lg": "zh_core_web_lg"}},
}


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _models_dir() -> Path:
    d = Path.home() / ".promptshield" / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_compatible_model_url(model_name: str) -> str:
    """Query spaCy's compatibility endpoint to get the download URL."""
    import json
    import urllib.request
    import spacy

    compat_url = "https://raw.githubusercontent.com/explosion/spacy-models/master/compatibility.json"
    with urllib.request.urlopen(compat_url, timeout=30) as resp:
        compat = json.loads(resp.read())

    spacy_version = spacy.about.__version__
    major_minor = ".".join(spacy_version.split(".")[:2])

    # Walk from most-specific to least-specific spaCy version key
    model_version = None
    for ver_key in [spacy_version, major_minor]:
        models = compat.get("spacy", {}).get(ver_key, {})
        versions = models.get(model_name, [])
        if versions:
            model_version = versions[0]
            break

    if model_version is None:
        raise RuntimeError(
            f"No compatible version of {model_name} found for spaCy {spacy_version}"
        )

    return (
        f"https://github.com/explosion/spacy-models/releases/download/"
        f"{model_name}-{model_version}/{model_name}-{model_version}-py3-none-any.whl"
    )


class ModelDownloadThread(QThread):
    """Background thread for downloading spaCy models.

    In a frozen (PyInstaller) app ``sys.executable`` is the bundle binary, not
    a Python interpreter.  In that case the model wheel is downloaded and
    extracted directly to ``~/.promptshield/models/``.
    """
    progress = Signal(str)
    finished_ok = Signal(str)
    finished_err = Signal(str)

    def __init__(self, model_name: str):
        super().__init__()
        self.model_name = model_name

    def run(self):
        try:
            self.progress.emit(f"Downloading {self.model_name}...")
            if _is_frozen():
                self._download_frozen()
            else:
                self._download_dev()
            self.finished_ok.emit(self.model_name)
        except Exception as e:
            self.finished_err.emit(str(e))

    def _download_dev(self):
        result = subprocess.run(
            [sys.executable, "-m", "spacy", "download", self.model_name],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "spacy download failed")

    def _download_frozen(self):
        """Download the model wheel and extract it into ~/.promptshield/models/."""
        import io
        import urllib.request
        import zipfile

        url = _get_compatible_model_url(self.model_name)
        self.progress.emit(f"Downloading {self.model_name} wheel…")

        with urllib.request.urlopen(url, timeout=600) as resp:
            data = resp.read()

        target = _models_dir()
        self.progress.emit(f"Extracting {self.model_name}…")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(target)


class SettingsTab(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._download_thread: ModelDownloadThread | None = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        main_layout = QVBoxLayout(container)

        # ── Entity Categories ──
        cat_group = QGroupBox("Entity Categories")
        cat_layout = QVBoxLayout(cat_group)
        self._cat_checkboxes: dict[str, QCheckBox] = {}
        enabled = self.config["enabled_categories"]
        for cat in ALL_CATEGORIES:
            cb = QCheckBox(cat)
            cb.setChecked(cat in enabled)
            cb.toggled.connect(self._on_categories_changed)
            cat_layout.addWidget(cb)
            self._cat_checkboxes[cat] = cb
        main_layout.addWidget(cat_group)

        # ── Sensitivity Threshold ──
        thresh_group = QGroupBox("Sensitivity Threshold")
        thresh_layout = QHBoxLayout(thresh_group)

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(int(self.config["sensitivity_threshold"] * 100))
        self.threshold_slider.valueChanged.connect(self._on_slider_changed)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setValue(self.config["sensitivity_threshold"])
        self.threshold_spin.valueChanged.connect(self._on_spin_changed)

        thresh_layout.addWidget(QLabel("Less aggressive"))
        thresh_layout.addWidget(self.threshold_slider)
        thresh_layout.addWidget(QLabel("More aggressive"))
        thresh_layout.addWidget(self.threshold_spin)
        main_layout.addWidget(thresh_group)

        # ── Language Models ──
        lang_group = QGroupBox("Language Models")
        lang_layout = QVBoxLayout(lang_group)

        self.lang_list = QListWidget()
        self.lang_list.itemChanged.connect(self._on_lang_toggled)
        lang_layout.addWidget(self.lang_list)

        btn_layout = QHBoxLayout()
        self.size_combo = QComboBox()
        self.size_combo.addItems(["sm (small, fast)", "lg (large, accurate)"])
        btn_layout.addWidget(self.size_combo)

        self.download_btn = QPushButton("Download")
        self.download_btn.clicked.connect(self._on_download)
        btn_layout.addWidget(self.download_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._on_remove)
        btn_layout.addWidget(self.remove_btn)
        lang_layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # indeterminate
        lang_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        lang_layout.addWidget(self.status_label)

        main_layout.addWidget(lang_group)

        # ── Save button ──
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._on_save)
        main_layout.addWidget(save_btn)

        main_layout.addStretch()
        scroll.setWidget(container)

        outer_layout = QVBoxLayout(self)
        outer_layout.addWidget(scroll)

        self._refresh_languages()

    def _on_categories_changed(self):
        enabled = [cat for cat, cb in self._cat_checkboxes.items() if cb.isChecked()]
        self.config["enabled_categories"] = enabled

    def _on_slider_changed(self, value: int):
        v = value / 100.0
        self.threshold_spin.blockSignals(True)
        self.threshold_spin.setValue(v)
        self.threshold_spin.blockSignals(False)
        self.config["sensitivity_threshold"] = v

    def _on_spin_changed(self, value: float):
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue(int(value * 100))
        self.threshold_slider.blockSignals(False)
        self.config["sensitivity_threshold"] = value

    def _on_lang_toggled(self, item: QListWidgetItem):
        code = item.data(Qt.ItemDataRole.UserRole)
        if code is None:
            return
        active = list(self.config["active_languages"])
        if item.checkState() == Qt.CheckState.Checked:
            if code not in active:
                active.append(code)
        else:
            active = [c for c in active if c != code]
        self.config["active_languages"] = active

    def get_active_languages(self) -> list[str]:
        """Return language codes that are both installed and checked."""
        return list(self.config["active_languages"])

    def _on_save(self):
        self.config.save()
        self.status_label.setText("Settings saved.")

    def _refresh_languages(self):
        self.lang_list.clear()
        for code, info in AVAILABLE_LANGUAGES.items():
            installed = self._is_model_installed(code)
            status = "Installed" if installed else "Not installed"
            item = QListWidgetItem(f"{info['name']} ({code}) — {status}")
            item.setData(Qt.ItemDataRole.UserRole, code)
            if installed:
                item.setCheckState(Qt.CheckState.Checked if code in self.config["active_languages"] else Qt.CheckState.Unchecked)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.lang_list.addItem(item)

    def _is_model_installed(self, lang_code: str) -> bool:
        """Check whether at least one model variant is available for *lang_code*.

        Works in three scenarios:
        1. Normal venv / development — spacy.util.is_package() succeeds.
        2. PyInstaller frozen bundle — the module is importable via hiddenimports.
        3. User-managed models in ~/.promptshield/models/.
        """
        import spacy
        from prompt_shield.core.anonymizer import _find_model_data_dir

        for size in ("sm", "lg"):
            name = AVAILABLE_LANGUAGES[lang_code]["models"][size]

            if spacy.util.is_package(name):
                return True

            try:
                mod = importlib.import_module(name)
                if _find_model_data_dir(Path(mod.__file__).parent) is not None:
                    return True
            except (ImportError, OSError):
                pass

        models_dir = Path.home() / ".promptshield" / "models"
        for size in ("sm", "lg"):
            name = AVAILABLE_LANGUAGES[lang_code]["models"][size]
            candidate = models_dir / name
            if candidate.is_dir() and _find_model_data_dir(candidate) is not None:
                return True

        return False

    def _on_download(self):
        item = self.lang_list.currentItem()
        if not item:
            return
        lang_code = item.data(Qt.ItemDataRole.UserRole)
        size = "sm" if self.size_combo.currentIndex() == 0 else "lg"
        model_name = AVAILABLE_LANGUAGES[lang_code]["models"][size]

        self.progress_bar.setVisible(True)
        self.download_btn.setEnabled(False)
        self.status_label.setText(f"Downloading {model_name}...")

        self._download_thread = ModelDownloadThread(model_name)
        self._download_thread.finished_ok.connect(self._on_download_ok)
        self._download_thread.finished_err.connect(self._on_download_err)
        self._download_thread.start()

    def _on_download_ok(self, model_name: str):
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        self.status_label.setText(f"Downloaded {model_name} successfully.")
        self._refresh_languages()

    def _on_download_err(self, error: str):
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error[:200]}")

    def _on_remove(self):
        item = self.lang_list.currentItem()
        if not item:
            return
        lang_code = item.data(Qt.ItemDataRole.UserRole)
        import shutil

        for size in ("sm", "lg"):
            model_name = AVAILABLE_LANGUAGES[lang_code]["models"][size]

            # Remove from ~/.promptshield/models/ if present
            user_model = _models_dir() / model_name
            if user_model.is_dir():
                shutil.rmtree(user_model, ignore_errors=True)

            # In dev mode also pip-uninstall the package
            if not _is_frozen():
                subprocess.run(
                    [sys.executable, "-m", "pip", "uninstall", "-y",
                     model_name.replace("_", "-")],
                    capture_output=True,
                )

        self.status_label.setText(f"Removed models for {lang_code}.")
        self._refresh_languages()
