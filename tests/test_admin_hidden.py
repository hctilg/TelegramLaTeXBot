from pathlib import Path

def test_admin_panel_supports_owner_and_added_admins() -> None:
  source = Path("app/bot.py").read_text(encoding="utf-8")
  assert "این بخش فقط برای ادمین است" not in source
  assert "await self.db.is_admin(user_id, self.settings.admin_id)" in source
  assert 'data == "admin:admins"' in source
  assert 'data == "admin:toggle_bot"' in source
