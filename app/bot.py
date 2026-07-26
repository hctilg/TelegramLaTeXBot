from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import quote

import asyncio, logging, re, secrets
from .api import TelegramAPI, TelegramAPIError, build_rich_message
from .config import Settings
from .database import Database, RequiredChannel
from .keyboards import (
  admin_main_keyboard,
  admins_manage_keyboard,
  broadcast_cancel_keyboard,
  broadcast_confirm_keyboard,
  channels_manage_keyboard,
  guest_join_keyboard,
  join_keyboard
)

from .utils import (
  channel_default_link,
  channel_id_from_message_link,
  escape,
  has_math_block,
  math_expressions,
  parse_channel_input,
  parse_rich_blocks,
  parse_rich_blocks_with_entities,
  validate_expression
)

logger = logging.getLogger(__name__)

UID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
UID_PATTERN = re.compile(r"^(?:uid[:\s-]*)?([A-Z2-9]{8,12})$", re.IGNORECASE)

@dataclass(slots=True)
class AdminState:
  name: str
  data: dict

class LatexGuestBot:
  def __init__(self, settings: Settings):
    self.settings = settings
    self.api = TelegramAPI(settings.bot_token, settings.bot_api_base)
    self.db = Database(settings.database_path)
    self.admin_states: dict[int, AdminState] = {}
    self.bot_id: int = 0
    self.bot_username: str = ""

  async def start(self):
    await self.db.initialize()
    me = await self.api.get_me()
    self.bot_id = int(me["id"])
    self.bot_username = str(me.get("username") or "")

    supports_guest = bool(me.get("supports_guest_queries"))
    logger.info("Bot started as @%s | guest mode=%s", self.bot_username, supports_guest)
    if not supports_guest:
      logger.warning("Guest Mode برای ربات فعال نیست؛ آن را در @BotFather فعال کن.")

    try:
      """
      " All old scopes are cleared so that `/admin` is no longer displayed in the command menu of any user, not even the owner.
      " But the owner can still issue the `/admin` command manually.
      """
      await self.api.reset_commands(self.settings.admin_id)
    
    except TelegramAPIError as exc:
      logger.warning("پاک‌سازی دستورات قدیمی ناموفق بود: %s", exc)

    try:
      await self.api.set_default_commands()

    except TelegramAPIError as exc:
      logger.warning("تنظیم دستور عمومی /start ناموفق بود: %s", exc)

    await self.polling()

  async def shutdown(self):
    await self.api.close()

  async def polling(self):
    offset: int | None = None
    while True:
      try:
        for update in await self.api.get_updates(offset):
          offset = int(update["update_id"]) + 1

          try:
            await self.process_update(update)

          except Exception:
            logger.exception("Unhandled update: %r", update)

      except TelegramAPIError as exc:
        logger.error("Polling API error: %s", exc)
        await asyncio.sleep(3)

      except (asyncio.CancelledError, KeyboardInterrupt):
        raise

      except Exception:
        logger.exception("Polling failure")
        await asyncio.sleep(3)

  async def process_update(self, update: dict):
    if inline_query := update.get("inline_query"):
      await self.handle_inline_query(inline_query)
      return

    if guest_message := update.get("guest_message"):
      await self.handle_guest_message(guest_message)
      return

    if callback := update.get("callback_query"):
      await self.handle_callback(callback)
      return

    if message := update.get("message"):
      await self.handle_message(message)

  async def create_saved_text_uid(self, user_id: int, raw_text: str, raw_entities: list[dict] | None = None):
    "The UID is not displayed to the user; it is only an internal identifier for saving, searching, and resubmitting previous formulas."
    existing_uid = await self.db.find_saved_text_uid(user_id, raw_text)
    if existing_uid:
      "If the text came from the PIW/Gest with Bold/Italic/Code/Custom Emoji, the new entities will also be stored on the same record."
      await self.db.touch_saved_text(existing_uid, raw_entities)
      return existing_uid

    for _ in range(20):
      uid = "".join(secrets.choice(UID_ALPHABET) for _ in range(9))
      if not await self.db.saved_text_exists(uid):
        await self.db.save_text(uid, user_id, raw_text, raw_entities)
        return uid

    raise RuntimeError("ساخت UID یکتا ناموفق بود.")

  @staticmethod
  def extract_uid(text: str):
    match = UID_PATTERN.fullmatch(text.strip())
    return match.group(1).upper() if match else None

  async def handle_message(self, message: dict):
    user = message.get("from")
    chat = message.get("chat") or {}

    if not user or user.get("is_bot"): return

    user_id = int(user["id"])
    chat_id = int(chat["id"])
    chat_type = chat.get("type")
    text = str(message.get("text") or "")
    await self.db.upsert_user(user)

    if chat_type != "private": return

    if text.startswith("/start"):
      await self.handle_start(chat_id, user)
      return

    is_admin = await self.db.is_admin(user_id, self.settings.admin_id)

    if text.startswith("/admin"):
      if not is_admin: return
      self.admin_states.pop(user_id, None)
      await self.show_admin_panel(chat_id, user_id)
      return

    if is_admin and user_id in self.admin_states:
      if await self.handle_admin_state(message): return

    if not is_admin and not await self.db.bot_enabled(): return

    """
    " Normal messages that are sent in response to a previous message, They should not be processed or duplicated as LaTeX formulas. 
    " Admin panel commands and inputs are managed above this section.
    """
    if message.get("reply_to_message"): return

    missing = await self.missing_channels(user_id)
    if missing:
      await self.send_join_required(chat_id, missing)
      return

    text_entities = list(message.get("entities") or message.get("caption_entities") or [])
    blocks = parse_rich_blocks_with_entities(text, text_entities)
    if not blocks or not has_math_block(blocks): return

    for expression in math_expressions(blocks):
      valid, error = validate_expression(expression)
      if not valid:
        await self.api.send_message(chat_id, f"⚠️ {escape(error)}")
        return

    try:
      await self.api.send_rich_blocks(chat_id, blocks)
      await self.create_saved_text_uid(user_id, text, text_entities)
      await self.api.send_message(
        chat_id,
        '<tg-emoji emoji-id="5411197345968701560">✅</tg-emoji> '
        '<b>فرمول ذخیره شد</b>\n\n'
        f'برای استفاده دوباره، فقط بنویس: <code>@{self.bot_username}</code>',
      )

    except TelegramAPIError as exc:
      await self.api.send_message(
        chat_id,
        "❌ تلگرام نتوانست این فرمول را رندر کند. کد LaTeX را بررسی کن.\n\n"
        f"<code>{escape(exc.description)}</code>",
      )

  async def handle_start(self, chat_id: int, user: dict):
    missing = await self.missing_channels(int(user["id"]))
    if missing:
      await self.send_join_required(chat_id, missing)
      return

    start_text = (
      '<tg-emoji emoji-id="6044079404307452322">✨</tg-emoji> '
      f'<b>@{self.bot_username}</b>\n'
      '<b>Send me your LaTeX formula:</b>\n\n'
      '<blockquote expandable>'
      '<b><tg-emoji emoji-id="5771868281212245617">📘</tg-emoji> آموزش استفاده</b>\n\n'
      'این ربات ابزار سریع نوشتن و نمایش فرمول‌های ریاضی با <b>LaTeX</b> است.\n\n'
      'با LaTeX می‌تونی کسرها، توان‌ها، رادیکال‌ها، ماتریس‌ها، انتگرال‌ها و '
      'فرمول‌های پیچیده رو به‌شکل مرتب و حرفه‌ای بنویسی.\n\n'
      'کافیه کد LaTeX رو برای ربات ارسال کنی:\n\n'
      '<code>\\frac{x^2+1}{\\sqrt{y}}</code>\n\n'
      'یا در هر گفت‌وگوی تلگرام، ربات رو به‌صورت Inline صدا بزنی:\n\n'
      f'<code>@{self.bot_username} '
      '\\int_0^1 x^2\\,dx</code>\n\n'
      '<tg-emoji emoji-id="5413621176402470664">👨‍💻</tg-emoji> '
      '<b>سازنده ربات:</b> @raha_423'
      '</blockquote>'
    )

    await self.api.send_message(chat_id, start_text)

  @staticmethod
  def _inline_preview(raw_text: str, limit: int = 64):
    preview = " ".join(raw_text.replace("\n", " ").split())
    return preview if len(preview) <= limit else preview[: limit - 1] + "…"

  @staticmethod
  def _latex_thumbnail_url(blocks: list[dict]):
    """Build a public GIF thumbnail URL for the first LaTeX expression.

    Telegram inline article results can display a remote thumbnail.  A white
    background is requested so the preview stays readable in both light and
    dark Telegram themes.  Very long expressions are omitted to avoid URLs
    that Telegram or the rendering service may reject.
    """
    expressions = math_expressions(blocks)
    if not expressions: return None

    expression = expressions[0].strip()
    if not expression or len(expression) > 900: return None

    render_expression = rf"\dpi{{160}}\bg_white \displaystyle {expression}"
    encoded = quote(render_expression, safe="")
    return f"https://latex.codecogs.com/gif.image?{encoded}"

  def _saved_inline_result(self, uid: str, raw_text: str, raw_entities: list[dict] | None = None):
    blocks = parse_rich_blocks_with_entities(raw_text, raw_entities, self.bot_username)
    if not blocks or not has_math_block(blocks): return None

    for expression in math_expressions(blocks):
      valid, _ = validate_expression(expression)
      if not valid: return None

    result: dict = {
      "type": "article",
      "id": f"saved-{uid}",
      "title": self._inline_preview(raw_text),
      "description": "برای ارسال دوباره لمس کن",
      "input_message_content": {
        "rich_message": build_rich_message(blocks),
      },
    }

    thumbnail_url = self._latex_thumbnail_url(blocks)

    if thumbnail_url:
      result.update(
        {
          "thumbnail_url": thumbnail_url,
          "thumbnail_width": 320,
          "thumbnail_height": 120,
        }
      )

    return result

  async def handle_inline_query(self, inline_query: dict):
    inline_query_id = str(inline_query.get("id") or "")
    if not inline_query_id: return

    user = inline_query.get("from") or {}
    if user and not user.get("is_bot"): await self.db.upsert_user(user)

    user_id = int(user.get("id", 0)) if user.get("id") else None
    raw_text = str(inline_query.get("query") or "").strip()

    if user_id is not None:
      is_admin = await self.db.is_admin(user_id, self.settings.admin_id)
      if not is_admin and not await self.db.bot_enabled():
        await self.api.answer_inline_text(
          inline_query_id,
          "⛔ ربات موقتاً خاموش است.",
          title="ربات خاموش است",
        )
        return

      missing = await self.missing_channels(user_id)
      if missing:
        await self.api.answer_inline_text(
          inline_query_id,
          "برای استفاده از ربات ابتدا عضو کانال‌های اجباری شو و سپس دوباره امتحان کن.",
          title="عضویت اجباری",
          description="برای ادامه وارد ربات شو و عضویت را تأیید کن.",
          reply_markup=guest_join_keyboard(missing, self.bot_username),
        )
        return

    """
    " Empty Query: Show the user's latest saved formulas.
    " Partial Query: Filter formulas by UID or LaTeX text.
    """
    if user_id is not None:
      saved_items = await self.db.list_saved_texts(user_id, query=raw_text, limit=30)
      saved_results = []
      for item in saved_items:
        result = self._saved_inline_result(item.uid, item.raw_text, item.raw_entities)
        if result is not None: saved_results.append(result)

      if saved_results:
        await self.api.answer_inline_saved_results(inline_query_id, saved_results)
        return

    if not raw_text:
      await self.api.answer_inline_text(
        inline_query_id,
        "هنوز فرمول ذخیره‌شده‌ای نداری. یک فرمول را همین‌جا بعد از نام ربات بنویس تا ذخیره شود.",
        title="فرمول ذخیره‌شده‌ای نیست",
        description="مثلاً بنویس: \frac{x^2+1}{\sqrt{y}}",
      )
      return

    # The exact UID can be loaded directly, even if the user got the UID from someone else.
    uid = self.extract_uid(raw_text)
    if uid:
      saved_item = await self.db.get_saved_text(uid)
      if saved_item is None:
        await self.api.answer_inline_text(
          inline_query_id,
          "❌ UID پیدا نشد یا معتبر نیست.",
          title="UID پیدا نشد",
        )
        return

      raw_text = saved_item.raw_text
      raw_entities = saved_item.raw_entities

    else: raw_entities = None

    # If the Query is a direct formula, send it as a ready result.
    blocks = parse_rich_blocks_with_entities(raw_text, raw_entities, self.bot_username)
    if not blocks or not has_math_block(blocks):
      await self.api.answer_inline_text(
        inline_query_id,
        "فرمول ذخیره‌شده یا LaTeX معتبری پیدا نشد.",
        title="نتیجه‌ای پیدا نشد",
        description="UID، بخشی از فرمول ذخیره‌شده یا کد LaTeX وارد کن.",
      )
      return

    for expression in math_expressions(blocks):
      valid, error = validate_expression(expression)
      if not valid:
        await self.api.answer_inline_text(
          inline_query_id,
          f"⚠️ {escape(error)}",
          title="خطای LaTeX",
        )
        return

    try:
      """
      " New formulas that the user writes directly in Inline are stored here.
      " (UID is created, but not displayed to the user.)
      """
      if user_id is not None:
        await self.create_saved_text_uid(user_id, raw_text, raw_entities)

      await self.api.answer_inline_rich_blocks(
        inline_query_id,
        blocks,
        title="LaTeX آماده ارسال",
        description="برای ارسال لمس کن",
        thumbnail_url=self._latex_thumbnail_url(blocks),
      )

    except TelegramAPIError as exc:
      logger.warning("Inline rich result failed: %s", exc)
      try:
        await self.api.answer_inline_text(
          inline_query_id,
          "❌ فرمول قابل رندر نبود. کد LaTeX را بررسی کن.",
          title="خطای رندر",
        )

      except TelegramAPIError:
        logger.exception("Inline fallback also failed")

  async def handle_guest_message(self, message: dict):
    guest_query_id = message.get("guest_query_id")
    if not guest_query_id: return

    user = message.get("from") or message.get("guest_bot_caller_user")
    if user and not user.get("is_bot"):
      await self.db.upsert_user(user)

    # # In Guest Mode, we also leave the regular Reply unanswered so that the user's text is not sent again in the form of a mathematical message from the bot.
    if message.get("reply_to_message"): return

    raw_text = str(message.get("text") or message.get("caption") or "").strip()
    raw_entities = list(message.get("entities") or message.get("caption_entities") or [])

    user_id = int(user["id"]) if user and user.get("id") else None
    if user_id is not None:
      if not await self.db.is_admin(user_id, self.settings.admin_id) and not await self.db.bot_enabled(): return
      missing = await self.missing_channels(user_id)
      if missing:
        text = "To use this bot, please join the channels below."
        await self.api.answer_guest_text(
          str(guest_query_id),
          text,
          reply_markup=guest_join_keyboard(missing, self.bot_username),
        )
        return

    uid = self.extract_uid(raw_text)

    if uid:
      saved_item = await self.db.get_saved_text(uid)
      if saved_item is None:
        await self.api.answer_guest_text(
          str(guest_query_id),
          "❌ UID پیدا نشد یا منقضی شده است.",
        )
        return

      raw_text = saved_item.raw_text
      raw_entities = saved_item.raw_entities or []

    blocks = parse_rich_blocks_with_entities(raw_text, raw_entities, self.bot_username)
    if not blocks or not has_math_block(blocks): return
    for expression in math_expressions(blocks):
      valid, error = validate_expression(expression)
      if not valid:
        await self.api.answer_guest_text(str(guest_query_id), f"⚠️ {escape(error)}")
        return

    try:
      await self.api.answer_guest_rich_blocks(str(guest_query_id), blocks)
      if user_id is not None:
        await self.create_saved_text_uid(user_id, raw_text, raw_entities)

    except TelegramAPIError as exc:
      logger.warning("Guest math failed: %s", exc)
      try:
        await self.api.answer_guest_text(
          str(guest_query_id),
          "❌ فرمول قابل رندر نبود. کد LaTeX را بررسی کن.",
        )

      except TelegramAPIError:
        logger.exception("Guest fallback also failed")

  async def handle_callback(self, callback: dict):
    callback_id = str(callback["id"])
    user = callback.get("from") or {}
    user_id = int(user.get("id", 0))
    data = str(callback.get("data") or "")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = int(chat.get("id", user_id))
    message_id = int(message.get("message_id", 0))

    if user and not user.get("is_bot"):
      await self.db.upsert_user(user)

    if data == "user:check_join":
      missing = await self.missing_channels(user_id)
      if missing:
        await self.api.answer_callback(callback_id, "هنوز عضو همه کانال‌ها نیستی.", show_alert=True)
        return

      await self.api.answer_callback(callback_id, "عضویت تأیید شد ✅")
      await self.api.edit_message(
        chat_id,
        message_id,
        "✅ عضویتت تأیید شد. حالا فرمول LaTeX را بفرست یا در هر چت ربات را منشن کن.",
      )
      return

    is_owner = user_id == self.settings.admin_id
    is_admin = await self.db.is_admin(user_id, self.settings.admin_id)

    if not is_admin:
      await self.api.answer_callback(callback_id)
      return

    await self.api.answer_callback(callback_id)

    if data == "admin:home":
      self.admin_states.pop(user_id, None)
      await self.edit_admin_panel(chat_id, message_id, user_id)

    elif data == "admin:toggle_bot":
      if not is_owner: return
      await self.db.toggle_bot()
      await self.edit_admin_panel(chat_id, message_id, user_id)

    elif data == "admin:admins":
      if not is_owner: return
      await self.show_admins_panel(chat_id, message_id)

    elif data == "admin:add_admin":
      if not is_owner: return
      self.admin_states[user_id] = AdminState("add_admin_wait_id", {})
      await self.api.edit_message(
        chat_id, message_id,
        '<b><tg-emoji emoji-id="5776159202649051327">🛡</tg-emoji>آیدی عددی ادمین جدیدتو بفرست</b>\n\nبرای لغو:\n/admin',
        reply_markup={"inline_keyboard": [[{"text": "لغو", "callback_data": "admin:home"}]]},
      )

    elif data.startswith("admin:delete_admin:"):
      if not is_owner: return
      admin_id = int(data.rsplit(":", 1)[1])
      await self.db.delete_admin(admin_id)
      await self.show_admins_panel(chat_id, message_id)

    elif data == "admin:broadcast":
      self.admin_states[user_id] = AdminState("broadcast_wait_message", {})
      await self.api.edit_message(
        chat_id,
        message_id,
        "<b>📢 ارسال همگانی</b>\n\nپیامی که می‌خواهی برای همه کپی شود را همین حالا بفرست. متن، عکس، ویدئو و فایل پشتیبانی می‌شود.",
        reply_markup=broadcast_cancel_keyboard(),
      )

    elif data == "admin:channels":
      self.admin_states.pop(user_id, None)
      await self.show_channels_panel(chat_id, message_id)

    elif data == "force:add":
      self.admin_states[user_id] = AdminState("force_add_channel_input", {})
      await self.api.edit_message(
        chat_id,
        message_id,
        "<b>➕ افزودن کانال جدید</b>\n\n"
        "یکی از موارد زیر را بفرست:\n"
        "• یوزرنیم عمومی مثل <code>@ChannelName</code>\n"
        "• آیدی عددی کانال مثل <code>-1001234567890</code>\n"
        "• لینک دعوت کانال خصوصی مثل <code>https://t.me/+AbCdEf...</code>\n\n"
        "قبلش ربات را داخل کانال ادمین کن.\n"
        "برای لغو: /admin",
        reply_markup={"inline_keyboard": [[{"text": "لغو", "callback_data": "admin:channels"}]]},
      )

    elif data.startswith("force:delete:"):
      channel_id = int(data.rsplit(":", 1)[1])
      await self.db.delete_channel(channel_id)
      channels = await self.db.list_channels()
      await self.api.edit_message(
        chat_id,
        message_id,
        "✅ کانال حذف شد.\n\nبرای حذف کانال دیگر، روی نام آن بزن.",
        reply_markup=channels_manage_keyboard(channels),
      )

    elif data == "broadcast:cancel":
      self.admin_states.pop(user_id, None)
      await self.edit_admin_panel(chat_id, message_id, user_id)

    elif data == "broadcast:confirm":
      state = self.admin_states.get(user_id)
      if not state or state.name != "broadcast_confirm":
        await self.api.send_message(chat_id, "پیام آماده‌ای برای ارسال وجود ندارد.")
        return

      self.admin_states.pop(user_id, None)
      await self.api.edit_message(chat_id, message_id, "⏳ ارسال همگانی شروع شد…", reply_markup={"inline_keyboard": []})
      success, failed = await self.broadcast(
        from_chat_id=int(state.data["chat_id"]),
        message_id=int(state.data["message_id"]),
      )

      await self.api.send_message(
        chat_id,
        "<b>✅ ارسال همگانی تمام شد</b>\n\n"
        f"موفق: <b>{success:,}</b>\n"
        f"ناموفق: <b>{failed:,}</b>",
        reply_markup=admin_main_keyboard(is_owner=user_id == self.settings.admin_id, is_on=await self.db.bot_enabled()),
      )

  async def handle_admin_state(self, message: dict):
    user_id = int(message["from"]["id"])
    chat_id = int(message["chat"]["id"])
    state = self.admin_states.get(user_id)
    if not state: return False

    if state.name == "broadcast_wait_message":
      self.admin_states[user_id] = AdminState(
        "broadcast_confirm",
        {"chat_id": chat_id, "message_id": int(message["message_id"])},
      )
      await self.api.send_message(
        chat_id,
        "<b>این پیام برای همه کاربران کپی شود؟</b>",
        reply_markup=broadcast_confirm_keyboard(),
      )
      return True

    if state.name == "add_admin_wait_id":
      raw = str(message.get("text") or "").strip()
      if not raw.isdigit():
        await self.api.send_message(chat_id, "❌ آیدی عددی معتبر بفرست یا /admin را بزن.")
        return True

      admin_id = int(raw)
      if admin_id == self.settings.admin_id:
        await self.api.send_message(chat_id, "این آیدی مالک رباته و از قبل دسترسی کامل داره.")
        self.admin_states.pop(user_id, None)
        return True

      try:
        await self.api.get_chat(admin_id)

      except TelegramAPIError:
        await self.api.send_message(chat_id, '<b><tg-emoji emoji-id="5805444407092058663">❌</tg-emoji>آیدی معتبر نیست یا کاربر هنوز ربات رو استارت نکرده.</b>')
        self.admin_states.pop(user_id, None)
        return True

      added = await self.db.add_admin(admin_id)
      self.admin_states.pop(user_id, None)

      if not added:
        await self.api.send_message(chat_id, "❌ این ادمین قبلاً اضافه شده.")

      else:
        await self.api.send_message(chat_id, '<b><tg-emoji emoji-id="5411197345968701560">✅</tg-emoji>ادمین جدید اضافه شد.</b>')

      return True

    if state.name == "force_add_channel_input":
      text = str(message.get("text") or "").strip()
      if not text:
        await self.api.send_message(chat_id, "یوزرنیم، آیدی یا لینک دعوت کانال را به‌صورت متن بفرست.")
        return True

      try:
        channel_hint, supplied_link = parse_channel_input(text)
        self.admin_states[user_id] = AdminState(
          "force_add_channel_verify",
          {"channel_hint": channel_hint, "supplied_link": supplied_link},
        )

        await self.api.send_message(
          chat_id,
          "<b>حالا آیدی کانال را مشخص کن</b>\n\n"
          "یکی از این دو کار را انجام بده:\n"
          "• یک پیام از همان کانال برای ربات فوروارد کن.\n"
          "• اگر فوروارد و دانلود در کانال بسته است، لینک یکی از پیام‌های کانال را بفرست.\n\n"
          "نمونه لینک خصوصی: <code>https://t.me/c/1234567890/25</code>\n"
          "نمونه لینک عمومی: <code>https://t.me/ChannelName/25</code>\n\n"
          "برای لغو: /admin",
        )

      except ValueError as exc:
        await self.api.send_message(
          chat_id,
          f"❌ ورودی نامعتبر است:\n<code>{escape(exc)}</code>\n\nدوباره بفرست یا /admin را بزن.",
        )

      return True

    if state.name == "force_add_channel_verify":
      try:
        resolved_chat_id = self._channel_id_from_forward(message)

        if resolved_chat_id is None:
          resolved_chat_id = channel_id_from_message_link(str(message.get("text") or message.get("caption") or ""))

        if resolved_chat_id is None:
          raise ValueError("یک پیام از خود کانال فوروارد کن یا لینک یکی از پیام‌های همان کانال را بفرست.")

        channel_hint = state.data.get("channel_hint")
        supplied_link = state.data.get("supplied_link")
        chat = await self.api.get_chat(resolved_chat_id)
        canonical_chat_id = str(chat.get("id") or resolved_chat_id)
        username = chat.get("username")

        if channel_hint:
          hinted_chat = await self.api.get_chat(channel_hint)
          hinted_id = str(hinted_chat.get("id") or channel_hint)
          if hinted_id != canonical_chat_id:
            raise ValueError("پیام یا لینک مربوط به کانالی که در مرحله قبل فرستادی نیست.")

        bot_member = await self.api.get_chat_member(canonical_chat_id, self.bot_id)
        if bot_member.get("status") not in {"administrator", "creator"}:
          raise ValueError("ربات داخل این کانال ادمین نیست.")

        invite_link = supplied_link or chat.get("invite_link") or channel_default_link(
          canonical_chat_id, username
        )

        if not invite_link:
          try:
            invite_link = await self.api.export_chat_invite_link(canonical_chat_id)

          except TelegramAPIError as exc:
            raise ValueError(
              "کانال خصوصی است و لینک دعوت پیدا نشد؛ دسترسی دعوت کاربر را به ربات بده."
            ) from exc

        title = str(chat.get("title") or username or canonical_chat_id)
        await self.db.add_channel(canonical_chat_id, title, str(invite_link))

        self.admin_states.pop(user_id, None)
        await self.api.send_message(
          chat_id,
          f"✅ کانال <b>{escape(title)}</b> اضافه شد.\nآیدی: <code>{escape(canonical_chat_id)}</code>",
          reply_markup=channels_manage_keyboard(await self.db.list_channels()),
        )

      except (ValueError, TelegramAPIError) as exc:
        detail = exc.description if isinstance(exc, TelegramAPIError) else str(exc)
        await self.api.send_message(
          chat_id,
          f"❌ کانال اضافه نشد:\n<code>{escape(detail)}</code>\n\n"
          "دوباره یک پیام از کانال فوروارد کن یا لینک یکی از پیام‌ها را بفرست. برای لغو: /admin",
        )

      return True

    return False

  @staticmethod
  def _channel_id_from_forward(message: dict):
    origin = message.get("forward_origin") or {}
    if origin.get("type") == "channel":
      chat = origin.get("chat") or {}
      if chat.get("id") is not None:
        return str(chat["id"])

    legacy_chat = message.get("forward_from_chat") or {}
    if legacy_chat.get("id") is not None:
      return str(legacy_chat["id"])

    return None

  async def show_admin_panel(self, chat_id: int, user_id: int):
    total, _active = await self.db.count_users()
    is_owner = user_id == self.settings.admin_id
    is_on = await self.db.bot_enabled()
    await self.api.send_message(
      chat_id,
      self.admin_panel_text(total),
      reply_markup=admin_main_keyboard(is_owner=is_owner, is_on=is_on),
    )

  async def edit_admin_panel(self, chat_id: int, message_id: int, user_id: int):
    total, _active = await self.db.count_users()
    await self.api.edit_message(
      chat_id,
      message_id,
      self.admin_panel_text(total),
      reply_markup=admin_main_keyboard(
        is_owner=user_id == self.settings.admin_id,
        is_on=await self.db.bot_enabled(),
      ),
    )

  @staticmethod
  def admin_panel_text(total_users: int):
    return (
      '<b>سلام عشق داداش<tg-emoji emoji-id="4918354603281482671">👋</tg-emoji></b>\n\n'
      '<tg-emoji emoji-id="5942877472163892475">👥</tg-emoji>'
      f'تعداد کاربرای ربات: {total_users:,}\n\n'
      'شنیدم اومدی منو مدیریت کنی،\nاز دکمه‌های زیر استفاده کن.'
    )

  async def show_admins_panel(self, chat_id: int, message_id: int):
    admin_ids = await self.db.list_admin_ids()
    text = (
      '<b><tg-emoji emoji-id="5413621176402470664">👮‍♂️</tg-emoji>مدیریت ادمین‌ها</b>\n\n'
      'از این بخش میتونی ادمین‌های ربات رو مدیریت کنی.\n\n'
      'برای حذف ادمین روی آیدیش بزن.'
    )
    await self.api.edit_message(
      chat_id, message_id, text, reply_markup=admins_manage_keyboard(admin_ids)
    )

  async def show_channels_panel(self, chat_id: int, message_id: int):
    channels = await self.db.list_channels()
    text = (
      '<b><tg-emoji emoji-id="5771868281212245617">📢</tg-emoji>مدیریت کانال‌ها</b>\n\n'
      'کانال‌های این بخش برای جوین اجباری استفاده میشن.\n\n'
      'برای حذف کانال روی اون کلیک کن.'
    )

    if not channels: text += '\n\nهنوز کانالی ثبت نشده.'

    await self.api.edit_message(
      chat_id, message_id, text, reply_markup=channels_manage_keyboard(channels)
    )

  async def missing_channels(self, user_id: int):
    if (
      (await self.db.is_admin(user_id, self.settings.admin_id)) or\
      (not await self.db.force_join_enabled())
    ): return []

    channels = await self.db.list_channels(active_only=True)
    missing: list[RequiredChannel] = []
    for channel in channels:
      try:
        member = await self.api.get_chat_member(channel.chat_id, user_id)
        status = member.get("status")
        is_member = status in {"member", "administrator", "creator"}
        if status == "restricted":
          is_member = bool(member.get("is_member"))

        if not is_member:
          missing.append(channel)

      except TelegramAPIError as exc:
        logger.warning("Membership check failed for %s: %s", channel.chat_id, exc)
        missing.append(channel)

    return missing

  async def send_join_required(self, chat_id: int, channels: list[RequiredChannel]):
    await self.api.send_message(
      chat_id,
      "To use this bot, please join the channels below.",
      reply_markup=join_keyboard(channels),
    )

  async def broadcast(self, from_chat_id: int, message_id: int) -> tuple[int, int]:
    user_ids = await self.db.get_user_ids()
    success = 0
    failed = 0

    for user_id in user_ids:
      try:
        await self.api.copy_message(from_chat_id, message_id, user_id)
        success += 1

      except TelegramAPIError as exc:
        failed += 1
        if exc.error_code == 403 or "blocked" in exc.description.lower() or "deactivated" in exc.description.lower():
          await self.db.mark_blocked(user_id, True)
          
        logger.info("Broadcast failed for %s: %s", user_id, exc)
      await asyncio.sleep(0.05)

    return success, failed
