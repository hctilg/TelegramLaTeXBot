from pathlib import Path

def test_reply_guard_is_present_in_both_handlers() -> None:
  source = Path("app/bot.py").read_text(encoding="utf-8")
  assert source.count('if message.get("reply_to_message")') >= 2