from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional, Tuple


SCHEMA = """
CREATE TABLE IF NOT EXISTS versions (
  version TEXT PRIMARY KEY,
  content_hash TEXT NOT NULL,
  content TEXT NOT NULL,
  posted_at TEXT,
  sent BOOLEAN DEFAULT FALSE
);
"""

MIGRATION_ADD_SENT_COLUMN = """
ALTER TABLE versions ADD COLUMN sent BOOLEAN DEFAULT FALSE;
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        logging.info(f"Initializing database at {self.path}")
        
        db_exists = self.path.exists()
        
        with self._conn() as conn:
            if db_exists:
                # Database exists, check if we need to migrate
                try:
                    conn.execute("SELECT sent FROM versions LIMIT 1")
                    logging.debug("Database already has sent column")
                except sqlite3.OperationalError:
                    logging.info("Adding sent column to existing database")
                    conn.execute(MIGRATION_ADD_SENT_COLUMN)
            else:
                # New database, create with full schema
                conn.executescript(SCHEMA)
                logging.info("Created new database with full schema")
        
        logging.info("Database schema created/verified")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_known_versions(self) -> set[str]:
        with self._conn() as conn:
            cur = conn.execute("SELECT version FROM versions")
            versions = {row[0] for row in cur.fetchall()}
            logging.debug(f"Retrieved {len(versions)} known versions from database")
            return versions

    def upsert_version(
        self,
        version: str,
        content_hash: str,
        content: str,
        posted_at: Optional[str] = None,
        sent: bool = False,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO versions(version, content_hash, content, posted_at, sent)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(version) DO UPDATE SET
                  content_hash=excluded.content_hash,
                  content=excluded.content,
                  posted_at=COALESCE(excluded.posted_at, versions.posted_at)
                """,
                (version, content_hash, content, posted_at, sent),
            )

    def mark_posted(self, version: str, posted_at_iso: str) -> None:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE versions SET posted_at=?, sent=TRUE WHERE version=?",
                (posted_at_iso, version),
            )
            rows_affected = cursor.rowcount
            logging.debug(f"Marked version {version} as posted, {rows_affected} rows affected")
            if rows_affected == 0:
                logging.warning(f"No rows updated when marking {version} as posted - version may not exist in DB")
    

    def unknown_versions(self, versions: Iterable[str]) -> list[str]:
        known = self.get_known_versions()
        return [v for v in versions if v not in known]
    
    def get_unsent_versions(self) -> list[str]:
        """Get versions that exist in DB but haven't been sent yet"""
        with self._conn() as conn:
            cur = conn.execute("SELECT version FROM versions WHERE sent = FALSE ORDER BY version")
            versions = [row[0] for row in cur.fetchall()]
            logging.debug(f"Found {len(versions)} unsent versions in database")
            return versions

