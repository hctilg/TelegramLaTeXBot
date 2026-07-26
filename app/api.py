from __future__ import annotations
import asyncio, logging, aiohttp

logger = logging.getLogger(__name__)

class TelegramAPIError(RuntimeError):
  def __init__(self, method: str, description: str, error_code: int | None = None):
    self.method = method
    self.description = description
    self.error_code = error_code
    super().__init__(f"Telegram API {method}: {description}")

class TelegramAPI:
  def __init__(self, token: str, api_base: str = "https://api.telegram.org"):
    self.base_url = f"{api_base}/bot{token}"
    timeout = aiohttp.ClientTimeout(total=70, connect=15, sock_read=65)
    self.session = aiohttp.ClientSession(timeout=timeout)

  async def close(self):
    await self.session.close()

  async def call(self, method: str, payload = None, *, retries: int = 2):
    url = f"{self.base_url}/{method}"
    payload = payload or {}

    for attempt in range(retries + 1):
      try:
        async with self.session.post(url, json=payload) as response:
          data = await response.json(content_type=None)
      except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        if attempt >= retries:
          raise TelegramAPIError(method, f"خطای شبکه: {exc}") from exc
        await asyncio.sleep(1.5 * (attempt + 1))
        continue

      if data.get("ok"):
        return data.get("result")

      error_code = data.get("error_code")
      description = data.get("description", "Unknown error")
      parameters = data.get("parameters") or {}
      retry_after = parameters.get("retry_after")

      if retry_after and attempt < retries:
        await asyncio.sleep(float(retry_after) + 0.2)
        continue

      raise TelegramAPIError(method, description, error_code)

    raise TelegramAPIError(method, "Unexpected API failure")

  async def get_updates(self, offset: int | None, timeout: int = 50):
    payload = {
      "timeout": timeout,
      "allowed_updates": ["message", "callback_query", "inline_query", "guest_message"],
    }
    
    if offset is not None: payload["offset"] = offset
    result = await self.call("getUpdates", payload, retries=3)
    return list(result or [])

  async def get_me(self):
    return await self.call("getMe")

  async def set_default_commands(self):
    await self.call(
      "setMyCommands",
      {
        "commands": [
          {"command": "start", "description": "Open LatexRM"}
        ]
      },
    )

  async def reset_commands(self, admin_chat_id: int):
    """Remove stale command menus left by older bot versions."""
    scopes = [
      {"type": "default"},
      {"type": "all_private_chats"},
      {"type": "all_group_chats"},
      {"type": "all_chat_administrators"},
      {"type": "chat", "chat_id": admin_chat_id},
    ]

    for scope in scopes:
      try:
        await self.call("deleteMyCommands", {"scope": scope})
      except TelegramAPIError as exc:
        """
        " Some scopes may not already exist for a bot
        " Or chat may not yet be accessible to the Bot API.
        " We'll continue with the rest.
        """
        logger.debug("Could not clear command scope %s: %s", scope, exc)

  async def send_message(self, chat_id: int | str, text: str, *, reply_markup = None, parse_mode: str = "HTML", disable_web_page_preview: bool = True):
    payload = {
      "chat_id": chat_id,
      "text": text,
      "parse_mode": parse_mode,
      "link_preview_options": {"is_disabled": disable_web_page_preview},
    }

    if reply_markup: payload["reply_markup"] = reply_markup
    
    return await self.call("sendMessage", payload)

  async def edit_message(self, chat_id: int | str, message_id: int, text: str, *, reply_markup = None, parse_mode: str = "HTML"):
    payload = {
      "chat_id": chat_id,
      "message_id": message_id,
      "text": text,
      "parse_mode": parse_mode,
      "link_preview_options": {"is_disabled": True},
    }

    if reply_markup is not None: payload["reply_markup"] = reply_markup
    
    return await self.call("editMessageText", payload)

  async def answer_callback(self, callback_query_id: str, text: str = "", *, show_alert: bool = False):
    payload = {
      "callback_query_id": callback_query_id,
      "show_alert": show_alert,
    }

    if text: payload["text"] = text
    return bool(await self.call("answerCallbackQuery", payload))

  async def get_chat(self, chat_id: int | str):
    return await self.call("getChat", {"chat_id": chat_id})

  async def get_chat_member(self, chat_id: int | str, user_id: int):
    return await self.call("getChatMember", {"chat_id": chat_id, "user_id": user_id})

  async def export_chat_invite_link(self, chat_id: int | str) -> str:
    return str(await self.call("exportChatInviteLink", {"chat_id": chat_id}))

  async def copy_message(self, from_chat_id: int, message_id: int, to_chat_id: int):
    return await self.call(
      "copyMessage",
      {
        "chat_id": to_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
      },
      retries=1,
    )

  async def send_rich_blocks(self, chat_id: int | str, blocks):
    return await self.call(
      "sendRichMessage",
      {
        "chat_id": chat_id,
        "rich_message": build_rich_message(blocks),
      },
    )

  async def answer_inline_rich_blocks(self, inline_query_id: str, blocks, *, title: str = "LaTeX", description: str = "ارسال فرمول LaTeX", thumbnail_url: str | None = None):
    result = {
      "type": "article",
      "id": "latex-rich-text",
      "title": title,
      "description": description,
      "input_message_content": {
        "rich_message": build_rich_message(blocks),
      },
    }

    if thumbnail_url:
      result.update(
        {
          "thumbnail_url": thumbnail_url,
          "thumbnail_width": 320,
          "thumbnail_height": 120,
        }
      )
    
    return bool(
      await self.call(
        "answerInlineQuery",
        {
          "inline_query_id": inline_query_id,
          "results": [result],
          "cache_time": 0,
          "is_personal": True,
        },
      )
    )

  async def answer_inline_saved_results(self, inline_query_id: str, results):
    """Answer an inline query with already-built rich-message article results."""
    return bool(
      await self.call(
        "answerInlineQuery",
        {
          "inline_query_id": inline_query_id,
          "results": results[:50],
          "cache_time": 0,
          "is_personal": True,
        },
      )
    )

  async def answer_inline_text(self, inline_query_id: str, text: str, *, title: str = "پیام ربات", description: str | None = None, reply_markup = None):
    result = {
      "type": "article",
      "id": "inline-notice",
      "title": title,
      "description": description or text.replace("\n", " ")[:120],
      "input_message_content": {
        "message_text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
      },
    }

    if reply_markup: result["reply_markup"] = reply_markup
    
    return bool(
      await self.call(
        "answerInlineQuery",
        {
          "inline_query_id": inline_query_id,
          "results": [result],
          "cache_time": 0,
          "is_personal": True,
        },
      )
    )

  async def answer_guest_rich_blocks(self, guest_query_id: str, blocks):
    result = {
      "type": "article",
      "id": "rich-text-latex",
      "title": "Rich Text",
      "input_message_content": {
        "rich_message": build_rich_message(blocks),
      },
    }

    return await self.call(
      "answerGuestQuery",
      {
        "guest_query_id": guest_query_id,
        "result": result,
      },
    )

  async def send_math(self, chat_id: int | str, expression: str):
    return await self.send_rich_blocks(
      chat_id,
      [{"type": "mathematical_expression", "expression": expression}],
    )

  async def answer_guest_math(self, guest_query_id: str, expression: str):
    return await self.answer_guest_rich_blocks(
      guest_query_id,
      [{"type": "mathematical_expression", "expression": expression}],
    )

  async def answer_guest_text(self, guest_query_id: str, text: str, *, reply_markup = None):
    result = {
      "type": "article",
      "id": "notice",
      "title": "پیام ربات",
      "input_message_content": {
        "message_text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
      },
    }

    if reply_markup: result["reply_markup"] = reply_markup

    return await self.call(
      "answerGuestQuery",
      {"guest_query_id": guest_query_id, "result": result},
    )

build_rich_message = lambda blocks : {
  "blocks": blocks,
  "skip_entity_detection": True,
}

build_rich_math = lambda expression : build_rich_message(
  [{"type": "mathematical_expression", "expression": expression}]
)
