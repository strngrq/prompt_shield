import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = Path.home() / ".promptshield" / "promptshield.db"


class Database:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    # ── schema ──────────────────────────────────────────────

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS mappings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                original_text TEXT    NOT NULL,
                hash         TEXT    NOT NULL UNIQUE,
                placeholder  TEXT    NOT NULL UNIQUE,
                category     TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS counters (
                category   TEXT PRIMARY KEY,
                next_index INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS block_list (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                text           TEXT    NOT NULL UNIQUE,
                prefix_match   INTEGER NOT NULL DEFAULT 0,
                case_sensitive INTEGER NOT NULL DEFAULT 0,
                added_at       TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS allow_list (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                text           TEXT    NOT NULL UNIQUE,
                prefix_match   INTEGER NOT NULL DEFAULT 0,
                case_sensitive INTEGER NOT NULL DEFAULT 0,
                added_at       TEXT    NOT NULL
            );
        """)

    # ── mappings ────────────────────────────────────────────

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_mapping_by_text(self, original_text: str) -> Optional[sqlite3.Row]:
        h = self._hash(original_text)
        return self._conn.execute(
            "SELECT * FROM mappings WHERE hash = ?", (h,)
        ).fetchone()

    def get_mapping_by_placeholder(self, placeholder: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM mappings WHERE placeholder = ?", (placeholder,)
        ).fetchone()

    def create_mapping(self, original_text: str, category: str) -> str:
        """Create a new mapping and return the placeholder string."""
        existing = self.get_mapping_by_text(original_text)
        if existing:
            return existing["placeholder"]

        idx = self._next_index(category)
        placeholder = f"{category}_{idx}"
        self._conn.execute(
            "INSERT INTO mappings (original_text, hash, placeholder, category, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (original_text, self._hash(original_text), placeholder, category, _now()),
        )
        self._conn.commit()
        return placeholder

    def _next_index(self, category: str) -> int:
        row = self._conn.execute(
            "SELECT next_index FROM counters WHERE category = ?", (category,)
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO counters (category, next_index) VALUES (?, 2)", (category,)
            )
            self._conn.commit()
            return 1
        idx = row["next_index"]
        self._conn.execute(
            "UPDATE counters SET next_index = ? WHERE category = ?", (idx + 1, category)
        )
        self._conn.commit()
        return idx

    def all_mappings(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM mappings ORDER BY id"
        ).fetchall()

    # ── block / allow lists ─────────────────────────────────

    def add_block(self, text: str, prefix_match: bool = False, case_sensitive: bool = False):
        self._conn.execute(
            "INSERT OR IGNORE INTO block_list (text, prefix_match, case_sensitive, added_at) "
            "VALUES (?, ?, ?, ?)",
            (text, int(prefix_match), int(case_sensitive), _now()),
        )
        self._conn.commit()

    def update_block(self, row_id: int, text: str, prefix_match: bool, case_sensitive: bool):
        self._conn.execute(
            "UPDATE block_list SET text = ?, prefix_match = ?, case_sensitive = ? WHERE id = ?",
            (text, int(prefix_match), int(case_sensitive), row_id),
        )
        self._conn.commit()

    def remove_block(self, row_id: int):
        self._conn.execute("DELETE FROM block_list WHERE id = ?", (row_id,))
        self._conn.commit()

    def all_blocks(self) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM block_list ORDER BY id").fetchall()

    def add_allow(self, text: str, prefix_match: bool = False, case_sensitive: bool = False):
        self._conn.execute(
            "INSERT OR IGNORE INTO allow_list (text, prefix_match, case_sensitive, added_at) "
            "VALUES (?, ?, ?, ?)",
            (text, int(prefix_match), int(case_sensitive), _now()),
        )
        self._conn.commit()

    def update_allow(self, row_id: int, text: str, prefix_match: bool, case_sensitive: bool):
        self._conn.execute(
            "UPDATE allow_list SET text = ?, prefix_match = ?, case_sensitive = ? WHERE id = ?",
            (text, int(prefix_match), int(case_sensitive), row_id),
        )
        self._conn.commit()

    def remove_allow(self, row_id: int):
        self._conn.execute("DELETE FROM allow_list WHERE id = ?", (row_id,))
        self._conn.commit()

    def all_allows(self) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM allow_list ORDER BY id").fetchall()

    # ── cleanup ─────────────────────────────────────────────

    def close(self):
        self._conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
