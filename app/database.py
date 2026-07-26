from __future__ import annotations
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
import aiosqlite, json

@dataclass(slots=True)
class RequiredChannel:
  id: int
  chat_id: str
  title: str
  invite_link: str
  is_active: bool

@dataclass(slots=True)
class SavedText:
  uid: str
  user_id: int
  raw_text: str
  raw_entities: list | None
  created_at: str
  last_used_at: str | None

class Database:
  def __init__(self, path: Path):
    self.path = path

  @asynccontextmanager
  async def connect(self):
    db = await aiosqlite.connect(self.path)
    db.row_factory = aiosqlite.Row

    try:
      await db.execute("PRAGMA journal_mode=WAL")
      await db.execute("PRAGMA foreign_keys=ON")
      yield db

    finally:
      await db.close()

  async def initialize(self):
    self.path.parent.mkdir(parents=True, exist_ok=True)
    async with self.connect() as db:
      await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          user_id INTEGER PRIMARY KEY,
          username TEXT,
          first_name TEXT NOT NULL DEFAULT '',
          joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          is_blocked INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS required_channels (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          chat_id TEXT NOT NULL UNIQUE,
          title TEXT NOT NULL,
          invite_link TEXT NOT NULL,
          is_active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admins (
          user_id INTEGER PRIMARY KEY,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS saved_texts (
          uid TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL,
          raw_text TEXT NOT NULL,
          raw_entities TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          last_used_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_saved_texts_user_id
        ON saved_texts(user_id);

        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('force_join_enabled', '1');
        INSERT OR IGNORE INTO settings(key, value)
        VALUES ('bot_enabled', '1');
        """
      )

      try:
        await db.execute("ALTER TABLE saved_texts ADD COLUMN raw_entities TEXT")
    
      except aiosqlite.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower(): raise
    
      await db.commit()

  async def upsert_user(self, user):
    user_id = int(user["id"])
    username = user.get("username")
    first_name = user.get("first_name") or ""
    async with self.connect() as db:
      await db.execute(
        """
        INSERT INTO users(user_id, username, first_name, is_blocked)
        VALUES (?, ?, ?, 0)
        ON CONFLICT(user_id) DO UPDATE SET
          username = excluded.username,
          first_name = excluded.first_name,
          last_seen_at = CURRENT_TIMESTAMP,
          is_blocked = 0
        """,
        (user_id, username, first_name),
      )
      await db.commit()

  async def mark_blocked(self, user_id: int, blocked: bool = True):
    async with self.connect() as db:
      await db.execute(
        "UPDATE users SET is_blocked = ? WHERE user_id = ?",
        (1 if blocked else 0, user_id),
      )
      await db.commit()

  async def count_users(self):
    async with self.connect() as db:
      cursor = await db.execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN is_blocked = 0 THEN 1 ELSE 0 END) AS active FROM users"
      )
      row = await cursor.fetchone()
      return int(row["total"] or 0), int(row["active"] or 0)

  async def get_user_ids(self, *, include_blocked: bool = False):
    sql = "SELECT user_id FROM users"
    if not include_blocked: sql += " WHERE is_blocked = 0"
    sql += " ORDER BY user_id"
    
    async with self.connect() as db:
      cursor = await db.execute(sql)
      rows = await cursor.fetchall()
      return [int(row["user_id"]) for row in rows]

  async def get_setting(self, key: str, default: str = ""):
    async with self.connect() as db:
      cursor = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
      row = await cursor.fetchone()
      return str(row["value"]) if row else default

  async def set_setting(self, key: str, value: str):
    async with self.connect() as db:
      await db.execute(
        """
        INSERT INTO settings(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
      )
      await db.commit()

  async def bot_enabled(self):
    return (await self.get_setting("bot_enabled", "1")) == "1"

  async def toggle_bot(self):
    new_value = not await self.bot_enabled()
    await self.set_setting("bot_enabled", "1" if new_value else "0")
    return new_value

  async def is_admin(self, user_id: int, owner_id: int | None = None):
    if owner_id is not None and int(user_id) == int(owner_id):
      return True
    async with self.connect() as db:
      cursor = await db.execute("SELECT 1 FROM admins WHERE user_id = ?", (int(user_id),))
      return await cursor.fetchone() is not None

  async def list_admin_ids(self):
    async with self.connect() as db:
      cursor = await db.execute("SELECT user_id FROM admins ORDER BY user_id")
      rows = await cursor.fetchall()
      return [int(row["user_id"]) for row in rows]

  async def add_admin(self, user_id: int):
    async with self.connect() as db:
      cursor = await db.execute("INSERT OR IGNORE INTO admins(user_id) VALUES (?)", (int(user_id),))
      await db.commit()
      return cursor.rowcount > 0

  async def delete_admin(self, user_id: int):
    async with self.connect() as db:
      await db.execute("DELETE FROM admins WHERE user_id = ?", (int(user_id),))
      await db.commit()

  async def save_text(self, uid: str, user_id: int, raw_text: str, raw_entities = None):
    entities_json = json.dumps(raw_entities, ensure_ascii=False) if raw_entities else None
    async with self.connect() as db:
      await db.execute(
        "INSERT INTO saved_texts(uid, user_id, raw_text, raw_entities) VALUES (?, ?, ?, ?)",
        (uid, int(user_id), raw_text, entities_json),
      )
      await db.commit()

  async def find_saved_text_uid(self, user_id: int, raw_text: str):
    """Return an existing UID for the same user/formula, if it was saved before."""
    async with self.connect() as db:
      cursor = await db.execute(
        """
        SELECT uid FROM saved_texts
        WHERE user_id = ? AND raw_text = ?
        ORDER BY COALESCE(last_used_at, created_at) DESC, created_at DESC
        LIMIT 1
        """,
        (int(user_id), raw_text),
      )

      row = await cursor.fetchone()
      return str(row["uid"]) if row else None

  async def touch_saved_text(self, uid: str, raw_entities = None):
    entities_json = json.dumps(raw_entities, ensure_ascii=False) if raw_entities else None
    async with self.connect() as db:
      if entities_json:
        await db.execute(
          "UPDATE saved_texts SET last_used_at = CURRENT_TIMESTAMP, raw_entities = ? WHERE uid = ?",
          (entities_json, uid),
        )
      else:
        await db.execute(
          "UPDATE saved_texts SET last_used_at = CURRENT_TIMESTAMP WHERE uid = ?",
          (uid,),
        )

      await db.commit()

  async def get_saved_text(self, uid: str):
    async with self.connect() as db:
      cursor = await db.execute(
        "SELECT uid, user_id, raw_text, raw_entities, created_at, last_used_at FROM saved_texts WHERE uid = ?",
        (uid,),
      )

      row = await cursor.fetchone()

      if row is None: return None

      await db.execute(
        "UPDATE saved_texts SET last_used_at = CURRENT_TIMESTAMP WHERE uid = ?",
        (uid,),
      )

      await db.commit()

      raw_entities = None
      if row["raw_entities"]:
        try: raw_entities = json.loads(str(row["raw_entities"]))
        except json.JSONDecodeError: raw_entities = None

      return SavedText(
        uid=str(row["uid"]),
        user_id=int(row["user_id"]),
        raw_text=str(row["raw_text"]),
        raw_entities=raw_entities,
        created_at=str(row["created_at"]),
        last_used_at=str(row["last_used_at"]) if row["last_used_at"] is not None else None,
      )

  async def saved_text_exists(self, uid: str):
    async with self.connect() as db:
      cursor = await db.execute(
        "SELECT 1 FROM saved_texts WHERE uid = ?",
        (uid,),
      )
      return await cursor.fetchone() is not None

  async def list_saved_texts(self, user_id: int, *, query: str = "", limit: int = 30):
    """Return the user's recent saved formulas, optionally filtered by UID/text."""
    safe_limit = max(1, min(int(limit), 50))
    normalized = query.strip()

    sql = (
      "SELECT uid, user_id, raw_text, raw_entities, created_at, last_used_at "
      "FROM saved_texts WHERE user_id = ?"
    )

    params = [int(user_id)]

    if normalized:
      sql += " AND (UPPER(uid) LIKE UPPER(?) OR raw_text LIKE ?)"
      pattern = f"%{normalized}%"
      params.extend([pattern, pattern])

    sql += (
      " ORDER BY COALESCE(last_used_at, created_at) DESC, created_at DESC "
      "LIMIT ?"
    )

    params.append(safe_limit)

    async with self.connect() as db:
      cursor = await db.execute(sql, params)
      rows = await cursor.fetchall()
      return [
        SavedText(
          uid=str(row["uid"]),
          user_id=int(row["user_id"]),
          raw_text=str(row["raw_text"]),
          raw_entities=(
            json.loads(str(row["raw_entities"]))
            if row["raw_entities"]
            else None
          ),
          created_at=str(row["created_at"]),
          last_used_at=(
            str(row["last_used_at"])
            if row["last_used_at"] is not None
            else None
          ),
        )
        for row in rows
      ]

  async def force_join_enabled(self):
    return (await self.get_setting("force_join_enabled", "1")) == "1"

  async def toggle_force_join(self):
    new_value = not await self.force_join_enabled()
    await self.set_setting("force_join_enabled", "1" if new_value else "0")
    return new_value

  async def add_channel(self, chat_id: str, title: str, invite_link: str):
    async with self.connect() as db:
      await db.execute(
        """
        INSERT INTO required_channels(chat_id, title, invite_link, is_active)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(chat_id) DO UPDATE SET
          title = excluded.title,
          invite_link = excluded.invite_link,
          is_active = 1
        """,
        (chat_id, title, invite_link),
      )
      await db.commit()

  async def delete_channel(self, channel_id: int):
    async with self.connect() as db:
      await db.execute("DELETE FROM required_channels WHERE id = ?", (channel_id,))
      await db.commit()

  async def list_channels(self, *, active_only: bool = False) -> list[RequiredChannel]:
    sql = "SELECT id, chat_id, title, invite_link, is_active FROM required_channels"
    if active_only: sql += " WHERE is_active = 1"
    sql += " ORDER BY id"

    async with self.connect() as db:
      cursor = await db.execute(sql)
      rows = await cursor.fetchall()
      return [
        RequiredChannel(
          id=int(row["id"]),
          chat_id=str(row["chat_id"]),
          title=str(row["title"]),
          invite_link=str(row["invite_link"]),
          is_active=bool(row["is_active"]),
        ) for row in rows
      ]
