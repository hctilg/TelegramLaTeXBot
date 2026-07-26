from __future__ import annotations
from dataclasses import dataclass
from dotenv import load_dotenv
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

@dataclass(frozen=True, slots=True)
class Settings:
  bot_token: str
  admin_id: int
  database_path: Path
  bot_api_base: str = "https://api.telegram.org"


def load_settings() -> Settings:
  token = os.getenv("BOT_TOKEN", "").strip()
  admin_id_raw = os.getenv("ADMIN_ID", "").strip()
  db_raw = os.getenv("DATABASE_PATH", "database.sqlite3").strip()
  api_base = os.getenv("BOT_API_BASE", "https://api.telegram.org").strip().rstrip("/")

  if not token or token == "123456789:PUT_YOUR_BOT_TOKEN_HERE":
    raise RuntimeError("BOT_TOKEN در فایل .env تنظیم نشده است.")
  if not admin_id_raw.isdigit():
    raise RuntimeError("ADMIN_ID باید شناسه عددی ادمین باشد.")

  database_path = Path(db_raw)
  if not database_path.is_absolute():
    database_path = BASE_DIR / database_path

  return Settings(
    bot_token=token,
    admin_id=int(admin_id_raw),
    database_path=database_path,
    bot_api_base=api_base,
  )
