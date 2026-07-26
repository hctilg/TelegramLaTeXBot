from __future__ import annotations
from .database import RequiredChannel

inline_keyboard = lambda rows : {"inline_keyboard": rows}

def _button(text: str, callback_data: str, *, emoji_id: str | None = None, style: str | None = None):
  button = {"text": text, "callback_data": callback_data}
  if emoji_id: button["icon_custom_emoji_id"] = emoji_id
  if style: button["style"] = style
  return button

def admin_main_keyboard(*, is_owner: bool, is_on: bool):
  rows = []
  if is_owner:
    rows.append([
      _button(
        "ربات روشنه" if is_on else "ربات خاموشه",
        "admin:toggle_bot",
        emoji_id="5318880799217431403" if is_on else "5805444407092058663",
        style="success" if is_on else "danger",
      )
    ])

    rows.append([
      _button("مدیریت ادمین‌ها", "admin:admins", emoji_id="5413621176402470664", style="primary"),
      _button("مدیریت کانال‌ها", "admin:channels", emoji_id="5771868281212245617", style="primary"),
    ])

  else:
    rows.append([
      _button("مدیریت کانال‌ها", "admin:channels", emoji_id="5771868281212245617", style="primary")
    ])

  rows.append([
    _button(
      "ارسال پیام همگانی",
      "admin:broadcast",
      emoji_id="5879841310902324730",
      style="success" if is_on else "danger",
    )
  ])

  return inline_keyboard(rows)

def admins_manage_keyboard(admin_ids: list[int]):
  rows, row = [], []
  for admin_id in admin_ids:
    row.append({"text": str(admin_id), "callback_data": f"admin:delete_admin:{admin_id}"})
    if len(row) == 2:
      rows.append(row)
      row = []
    
  if row: rows.append(row)

  rows.append([
    _button("افزودن ادمین", "admin:add_admin", emoji_id="5413621176402470664", style="primary")
  ])

  rows.append([{"text": "◀️ بازگشت", "callback_data": "admin:home"}])

  return inline_keyboard(rows)

def channels_manage_keyboard(channels: list[RequiredChannel]):
  rows, row = [], []
  for channel in channels:
    row.append({"text": channel.title, "callback_data": f"force:delete:{channel.id}"})
    if len(row) == 2:
      rows.append(row)
      row = []

  if row: rows.append(row)

  rows.append([
    _button("افزودن کانال", "force:add", emoji_id="5771868281212245617", style="primary")
  ])

  rows.append([{"text": "◀️ بازگشت", "callback_data": "admin:home"}])

  return inline_keyboard(rows)

broadcast_cancel_keyboard = lambda : inline_keyboard([[{"text": "لغو", "callback_data": "broadcast:cancel"}]])

broadcast_confirm_keyboard = lambda : inline_keyboard([[ 
  {"text": "✅ ارسال", "callback_data": "broadcast:confirm"},
  {"text": "❌ لغو", "callback_data": "broadcast:cancel"},
]])

def join_keyboard(channels: list[RequiredChannel]):
  rows = []
  for channel in channels:
    rows.append([{"text": f"Join {channel.title}", "url": channel.invite_link}])

  rows.append([{"text": "✅ I Joined", "callback_data": "user:check_join"}])
  
  return inline_keyboard(rows)


def guest_join_keyboard(channels: list[RequiredChannel], bot_username: str):
  rows = []
  for channel in channels:
    rows.append([{"text": f"Join {channel.title}", "url": channel.invite_link}])

  rows.append([{"text": "Check Membership", "url": f"https://t.me/{bot_username}?start=check"}])
  
  return inline_keyboard(rows)