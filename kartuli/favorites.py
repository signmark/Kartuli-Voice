"""User-scoped favorite phrases and their saved audio files."""

from contextlib import closing
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4


CATEGORIES = (
    ("greetings", "Приветствия"),
    ("food", "Кафе и еда"),
    ("transport", "Транспорт"),
    ("shopping", "Покупки"),
    ("emergency", "Экстренное"),
    ("other", "Другое"),
)
CATEGORY_LABELS = dict(CATEGORIES)
DEFAULT_DB_PATH = "data/favorites.sqlite3"


@dataclass(frozen=True)
class Favorite:
    id: int
    user_id: int
    source_text: str
    georgian_text: str
    category: str
    audio_path: Path


class FavoriteStore:
    """Open a short-lived SQLite connection per operation so a lost DB is recreated."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        configured = db_path or os.getenv("FAVORITES_DB_PATH", DEFAULT_DB_PATH)
        self.db_path = Path(configured).expanduser().resolve()
        self.audio_dir = self.db_path.parent / "audio"

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        recreated = not self.db_path.exists()
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                source_text TEXT NOT NULL,
                georgian_text TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN
                    ('greetings', 'food', 'transport', 'shopping', 'emergency', 'other')),
                audio_path TEXT NOT NULL,
                UNIQUE (user_id, georgian_text)
            )"""
        )
        self.db_path.chmod(0o600)
        if recreated and self.audio_dir.exists():
            for orphan in self.audio_dir.glob("*.mp3"):
                orphan.unlink(missing_ok=True)
        return connection

    @staticmethod
    def _favorite(row: sqlite3.Row) -> Favorite:
        return Favorite(
            id=row["id"],
            user_id=row["user_id"],
            source_text=row["source_text"],
            georgian_text=row["georgian_text"],
            category=row["category"],
            audio_path=Path(row["audio_path"]),
        )

    def get(self, user_id: int, card_id: int) -> Favorite | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM favorites WHERE user_id = ? AND id = ?", (user_id, card_id)
            ).fetchone()
        return self._favorite(row) if row else None

    def find(self, user_id: int, georgian_text: str) -> Favorite | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM favorites WHERE user_id = ? AND georgian_text = ?",
                (user_id, georgian_text),
            ).fetchone()
        return self._favorite(row) if row else None

    def list_category(self, user_id: int, category: str) -> list[Favorite]:
        if category not in CATEGORY_LABELS:
            raise ValueError("Unknown favorite category")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM favorites WHERE user_id = ? AND category = ? ORDER BY id DESC",
                (user_id, category),
            ).fetchall()
        return [self._favorite(row) for row in rows]

    def counts(self, user_id: int) -> dict[str, int]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT category, COUNT(*) AS total FROM favorites WHERE user_id = ? GROUP BY category",
                (user_id,),
            ).fetchall()
        return {row["category"]: row["total"] for row in rows}

    def add(
        self, user_id: int, source_text: str, georgian_text: str, category: str, audio_source: str | Path
    ) -> tuple[Favorite, bool]:
        if category not in CATEGORY_LABELS:
            raise ValueError("Unknown favorite category")
        existing = self.find(user_id, georgian_text)
        if existing:
            return existing, False

        self.audio_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        audio_path = self.audio_dir / f"{uuid4().hex}.mp3"
        try:
            shutil.copyfile(audio_source, audio_path)
            audio_path.chmod(0o600)
            if audio_path.stat().st_size == 0:
                raise ValueError("Empty favorite audio")
            with closing(self._connect()) as connection:
                with connection:
                    cursor = connection.execute(
                        "INSERT INTO favorites (user_id, source_text, georgian_text, category, audio_path) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (user_id, source_text, georgian_text, category, str(audio_path)),
                    )
                    card_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            audio_path.unlink(missing_ok=True)
            existing = self.find(user_id, georgian_text)
            if existing:
                return existing, False
            raise
        except Exception:
            audio_path.unlink(missing_ok=True)
            raise
        card = self.get(user_id, card_id)
        assert card is not None
        return card, True

    def delete(self, user_id: int, card_id: int) -> bool:
        card = self.get(user_id, card_id)
        if not card:
            return False
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM favorites WHERE user_id = ? AND id = ?", (user_id, card_id)
                )
        card.audio_path.unlink(missing_ok=True)
        return True
