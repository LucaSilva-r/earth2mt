"""SQLite map.sqlite writer for Luanti worlds.

Uses the modern schema (separate x, y, z columns) from Luanti 5.12+.
"""

import os
import sqlite3


class WorldDB:
    def __init__(self, world_path: str):
        db_path = os.path.join(world_path, "map.sqlite")
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA synchronous = OFF")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS `blocks` ("
            "  `x` INTEGER, `y` INTEGER, `z` INTEGER,"
            "  `data` BLOB NOT NULL,"
            "  PRIMARY KEY (`x`, `z`, `y`)"
            ")"
        )
        self.db.commit()

    def begin(self):
        self.db.execute("BEGIN")

    def end(self):
        self.db.commit()

    def save_block(self, x: int, y: int, z: int, data: bytes):
        """Save a serialized MapBlock at the given MapBlock coordinates."""
        self.db.execute(
            "INSERT OR REPLACE INTO `blocks` (`x`, `y`, `z`, `data`) VALUES (?, ?, ?, ?)",
            (x, y, z, data),
        )

    def close(self):
        self.db.commit()
        self.db.close()
