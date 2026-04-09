import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".promptshield" / "config.json"

DEFAULTS: dict[str, Any] = {
    "enabled_categories": [
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
    ],
    "sensitivity_threshold": 0.35,
    "active_languages": ["en"],
    "models_dir": str(Path.home() / ".promptshield" / "models"),
}


class Config:
    def __init__(self, path: Path = DEFAULT_CONFIG_PATH):
        self._path = path
        self._data: dict[str, Any] = dict(DEFAULTS)
        self._load()

    def _load(self):
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            self._data.update(stored)

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any):
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)
