from __future__ import annotations
from urllib.parse import urlparse
import html, re

MENTION_RE_TEMPLATE = r"^\s*@{username}\b\s*"

MATH_WRAPPERS = (
  ("<tg-math-block>", "</tg-math-block>"),
  ("$$", "$$"),
  ("\\[", "\\]"),
  ("$", "$"),
  ("\\(", "\\)"),
)

LATEX_COMMAND_RE = re.compile(r"\\([A-Za-z]+)")
LATEX_COMMANDS = {
  "displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle",
  "frac", "dfrac", "tfrac", "sqrt", "sum", "prod", "coprod",
  "int", "iint", "iiint", "oint", "lim", "log", "ln",
  "sin", "cos", "tan", "cot", "sec", "csc", "min", "max",
  "det", "gcd", "left", "right", "begin", "end", "cases",
  "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix",
  "overline", "underline", "hat", "widehat", "bar", "vec",
  "dot", "ddot", "mathbf", "mathrm", "mathbb", "mathcal",
  "mathsf", "mathtt", "operatorname", "text",
  "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon",
  "zeta", "eta", "theta", "vartheta", "iota", "kappa", "lambda",
  "mu", "nu", "xi", "pi", "varpi", "rho", "varrho", "sigma",
  "varsigma", "tau", "upsilon", "phi", "varphi", "chi", "psi",
  "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi",
  "Sigma", "Upsilon", "Phi", "Psi", "Omega",
  "infty", "partial", "nabla", "cdot", "times", "div", "pm",
  "mp", "le", "leq", "ge", "geq", "ne", "neq", "approx",
  "equiv", "in", "notin", "subset", "supset", "subseteq",
  "supseteq", "cup", "cap", "land", "lor", "forall", "exists",
  "to", "rightarrow", "leftarrow", "Rightarrow", "Leftarrow",
  "Leftrightarrow", "mapsto", "quad", "qquad", "ldots", "cdots",
  "vdots", "ddots", "binom", "choose",
}
LATEX_SYMBOL_RE = re.compile(r"\\[{}_^%#$&]")
SUPERSCRIPT_OR_SUBSCRIPT_RE = re.compile(r"[_^]\s*(?:\{[^{}]+\}|[A-Za-z0-9])")
UNICODE_MATH_RE = re.compile(r"[∑∫√∞≈≠≤≥±×÷∂∆∇∏]")
KNOWN_MATH_FUNCTION_RE = re.compile(
  r"\b(?:sin|cos|tan|cot|sec|csc|log|ln|exp|lim|max|min|det|gcd)\s*\(",
  re.IGNORECASE,
)
MATH_ONLY_RE = re.compile(r"^[0-9A-Za-z\s+\-*/=<>^_{}()\[\].,|!:]+$")
COMPACT_MATH_RE = re.compile(
  r"(?<![A-Za-z0-9_])"
  r"(?:[A-Za-z0-9]+(?:[_^](?:\{[^{}]+\}|[A-Za-z0-9]))*)"
  r"(?:\s*[=<>+\-*/]\s*"
  r"(?:[A-Za-z0-9]+(?:[_^](?:\{[^{}]+\}|[A-Za-z0-9]))*))+"
)

EXPLICIT_WRAPPER_PATTERNS = (
  re.compile(r"<tg-math-block>(.*?)</tg-math-block>", re.IGNORECASE | re.DOTALL),
  re.compile(r"<tg-math>(.*?)</tg-math>", re.IGNORECASE | re.DOTALL),
  re.compile(r"\$\$(.*?)\$\$", re.DOTALL),
  re.compile(r"\\\[(.*?)\\\]", re.DOTALL),
  re.compile(r"\\\((.*?)\\\)", re.DOTALL),
)

RICH_MATH_WRAPPER_RE = re.compile(
  r"<tg-math-block>(?P<html_block>.*?)</tg-math-block>"
  r"|<tg-math>(?P<html_inline>.*?)</tg-math>"
  r"|\$\$(?P<double_dollar>.*?)\$\$"
  r"|\\\[(?P<bracket>.*?)\\\]"
  r"|\\\((?P<paren>.*?)\\\)"
  r"|(?<!\$)\$(?!\$)(?P<single_dollar>.+?)(?<!\$)\$(?!\$)",
  re.IGNORECASE | re.DOTALL,
)

escape = lambda value : html.escape(str(value), quote=True)

def normalize_expression(text: str, bot_username: str | None = None):
  value = text.strip()

  if bot_username:
    pattern = MENTION_RE_TEMPLATE.format(username=re.escape(bot_username.lstrip("@")))
    value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()

  for left, right in MATH_WRAPPERS:
    if value.startswith(left) and value.endswith(right) and len(value) > len(left) + len(right):
      value = value[len(left) : -len(right)].strip()
      break

  return value

def is_latex_expression(text: str, bot_username: str | None = None):
  """Return True only when the message looks like an actual math/LaTeX expression.

  Plain conversational text is intentionally ignored. Explicit math wrappers,
  LaTeX commands, powers/indices, common mathematical symbols, and compact
  equations such as ``E=mc^2`` are accepted.
  """
  value = text.strip()
  if bot_username:
    pattern = MENTION_RE_TEMPLATE.format(username=re.escape(bot_username.lstrip("@")))
    value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()

  if not value: return False

  for left, right in MATH_WRAPPERS:
    if value.startswith(left) and value.endswith(right) and len(value) > len(left) + len(right):
      return True

  expression = normalize_expression(value)
  if not expression: return False

  if (
    any(match.group(1) in LATEX_COMMANDS for match in LATEX_COMMAND_RE.finditer(expression)) or\
    LATEX_SYMBOL_RE.search(expression) or\
    SUPERSCRIPT_OR_SUBSCRIPT_RE.search(expression) or\
    UNICODE_MATH_RE.search(expression) or\
    KNOWN_MATH_FUNCTION_RE.search(expression)
  ): return True

  # Accept compact equations/arithmetic, while rejecting normal sentences.
  if not MATH_ONLY_RE.fullmatch(expression): return False

  operators = set("=<>+-*/^_")
  if not any(char in operators for char in expression): return False

  words = re.findall(r"[A-Za-z]+", expression)
  has_number = any(char.isdigit() for char in expression)
  has_number_and_operator = has_number and any(char in expression for char in "+-*/=<>^_")
  short_symbolic_terms = bool(words) and all(len(word) <= 2 for word in words)
  has_relation = any(char in expression for char in "=<>^_")

  return has_number_and_operator or short_symbolic_terms or (has_relation and has_number)

def extract_latex_expression(text: str, bot_username: str | None = None):
  r"""Extract only the actual LaTeX/math part from a mixed message.

  Example: ``@Bot hello\n\n\displaystyle\sum...`` returns only the
  formula line. Plain text before or after the formula is ignored.
  """
  value = text.strip()
  if bot_username:
    pattern = MENTION_RE_TEMPLATE.format(username=re.escape(bot_username.lstrip("@")))
    value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()

  if not value: return ""

  # Explicit Telegram/Markdown math wrappers may appear inside surrounding text.
  for pattern in EXPLICIT_WRAPPER_PATTERNS:
    match = pattern.search(value)
    if match:
      candidate = match.group(1).strip()
      if candidate and is_latex_expression(candidate): return candidate

  groups: list[list[str]] = []
  current: list[str] = []

  for raw_line in value.splitlines():
    line = raw_line.strip()
    if not line:
      if current:
        groups.append(current)
        current = []
      continue

    candidate = ""

    # If a line contains ordinary text before a real LaTeX command, start
    # exactly from the first recognized command.
    command_matches = [
      match for match in LATEX_COMMAND_RE.finditer(line)
      if match.group(1) in LATEX_COMMANDS
    ]

    if command_matches: candidate = line[command_matches[0].start():].strip()
    else:
      # Prefer extracting a compact equation from surrounding prose, e.g.
      # ``please render E=mc^2`` -> ``E=mc^2``.
      compact = COMPACT_MATH_RE.search(line)
      if compact and is_latex_expression(compact.group(0)): candidate = compact.group(0).strip()
      elif is_latex_expression(line): candidate = line

    if candidate and is_latex_expression(candidate): current.append(candidate)
    elif current:
      groups.append(current)
      current = []

  if current: groups.append(current)

  if not groups: return ""

  def score(group: list[str]) -> tuple[int, int]:
    joined = "\n".join(group)
    commands = sum(
      1 for match in LATEX_COMMAND_RE.finditer(joined)
      if match.group(1) in LATEX_COMMANDS
    )

    return commands * 100 + len(group) * 10 + len(joined), len(joined)

  best = max(groups, key=score)
  return "\n".join(best).strip()

def strip_bot_mention(text: str, bot_username: str | None = None):
  """Remove only the leading @bot mention and keep the user's content."""
  value = text.strip()
  if bot_username:
    pattern = MENTION_RE_TEMPLATE.format(username=re.escape(bot_username.lstrip("@")))
    value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()

  return value

def _append_rich_block(blocks: list[dict[str, object]], block_type: str, content: str):
  value = content.strip()
  if not value: return

  if block_type == "paragraph":
    if blocks and blocks[-1].get("type") == "paragraph":
      previous = str(blocks[-1].get("text") or "")
      blocks[-1]["text"] = f"{previous}\n{value}" if previous else value
    else:
      blocks.append({"type": "paragraph", "text": value})

    return

  blocks.append({"type": "mathematical_expression", "expression": value})


def _parse_unwrapped_rich_chunk(chunk: str, blocks: list[dict[str, object]]):
  """Parse text outside explicit math wrappers while preserving plain text."""
  text_buffer: list[str] = []

  def flush_text():
    if text_buffer:
      _append_rich_block(blocks, "paragraph", "\n".join(text_buffer))
      text_buffer.clear()

  for raw_line in chunk.splitlines():
    line = raw_line.strip()
    if not line:
      flush_text()
      continue

    command_matches = [
      match
      for match in LATEX_COMMAND_RE.finditer(line)
      if match.group(1) in LATEX_COMMANDS
    ]

    if command_matches:
      first = command_matches[0]
      prefix = line[: first.start()].strip()
      expression = line[first.start() :].strip()
      
      if prefix: text_buffer.append(prefix)
      flush_text()

      if is_latex_expression(expression): _append_rich_block(blocks, "math", normalize_expression(expression))
      else: text_buffer.append(expression)
      continue

    matches = [
      match
      for match in COMPACT_MATH_RE.finditer(line)
      if is_latex_expression(match.group(0))
    ]

    if matches:
      cursor = 0
      for match in matches:
        prefix = line[cursor : match.start()].strip()
        
        if prefix: text_buffer.append(prefix)
        flush_text()

        _append_rich_block(blocks, "math", normalize_expression(match.group(0)))
        cursor = match.end()
        
      suffix = line[cursor:].strip()

      if suffix: text_buffer.append(suffix)
      continue

    if is_latex_expression(line):
      flush_text()
      _append_rich_block(blocks, "math", normalize_expression(line))
      continue

    text_buffer.append(line)

  flush_text()

def parse_rich_blocks(text: str, bot_username: str | None = None):
  """Build ordered Rich Message blocks from mixed plain text and LaTeX.

  Plain text is kept as paragraph blocks. Only detected LaTeX/math fragments are
  converted to ``mathematical_expression`` blocks. The caller should send the
  result only when at least one mathematical block exists.
  """
  value = strip_bot_mention(text, bot_username)
  if not value: return []

  blocks: list[dict[str, object]] = []
  cursor = 0

  for match in RICH_MATH_WRAPPER_RE.finditer(value):
    before = value[cursor : match.start()]
    if before:
      _parse_unwrapped_rich_chunk(before, blocks)

    expression = next(
      (group for group in match.groups() if group is not None),
      "",
    ).strip()

    if expression and is_latex_expression(expression): _append_rich_block(blocks, "math", normalize_expression(expression))
    else: _append_rich_block(blocks, "paragraph", match.group(0))
    cursor = match.end()

  remainder = value[cursor:]
  if remainder: _parse_unwrapped_rich_chunk(remainder, blocks)

  return blocks

def has_math_block(blocks: list[dict[str, object]]):
  return any(block.get("type") == "mathematical_expression" for block in blocks)

def math_expressions(blocks: list[dict[str, object]]) -> list[str]:
  return [
    str(block.get("expression") or "")
    for block in blocks
    if block.get("type") == "mathematical_expression"
  ]

def validate_expression(expression: str):
  if not expression: return False, "بعد از نام ربات، فرمول LaTeX را بنویس."
  if len(expression) > 4000: return False, "فرمول خیلی طولانی است؛ حداکثر ۴۰۰۰ کاراکتر بفرست."
  if "\x00" in expression: return False, "فرمول نامعتبر است."

  unknown_commands = [
    match.group(1)
    for match in LATEX_COMMAND_RE.finditer(expression)
    if match.group(1) not in LATEX_COMMANDS
  ]

  if unknown_commands:
    command = unknown_commands[0]
    if "sqrt".startswith(command.lower()):
      return False, f"فرمول ناقصه؛ دستور \\{command} کامل نیست. شاید منظورت \\sqrt{{}} بوده."
    
    return False, f"دستور \\{command} شناخته نشد یا ناقص است. نام دستور را کامل بنویس."

  brace_balance = 0
  for char in expression:
    if char == "{": brace_balance += 1
    elif char == "}": brace_balance -= 1
    if brace_balance < 0: return False, "یک آکولاد اضافه بسته شده. ساختار { } را بررسی کن."
  
  if brace_balance > 0:
    return False, "فرمول ناقصه؛ یک یا چند آکولاد { } بسته نشده."

  if expression.count("\\left") != expression.count("\\right"):
    return False, "برای هر \\left باید یک \\right هم داشته باشی."

  return True, ""

def parse_channel_input(text: str):
  """Parse channel username/id/invite link for the first add step."""
  value = text.strip()

  # Backward-compatible form: -100... | https://t.me/+...
  parts = [part.strip() for part in value.split("|", maxsplit=1)]
  if len(parts) == 2:
    chat_hint, invite_link = parts
    if not (chat_hint.startswith("-100") and chat_hint[1:].isdigit()):
      raise ValueError("شناسه عددی کانال نامعتبر است.")

    parsed = urlparse(invite_link)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
      "t.me", "telegram.me", "www.t.me"
    }:
      raise ValueError("لینک عضویت باید از دامنه t.me باشد.")
    
    return chat_hint, invite_link

  if value.startswith("-100"):
    if not value[1:].isdigit():
      raise ValueError("شناسه عددی کانال نامعتبر است.")

    return value, None

  if value.startswith("@"):
    if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
      raise ValueError("یوزرنیم کانال نامعتبر است.")
    
    return value, None

  parsed = urlparse(value)
  if parsed.scheme in {"http", "https"} and parsed.netloc.lower() in {
    "t.me", "telegram.me", "www.t.me"
  }:
    path = parsed.path.strip("/")
    if path.startswith("+") or path.startswith("joinchat/"):
      return None, value
    
    raise ValueError("در مرحله اول فقط لینک دعوت خصوصی مثل https://t.me/+AbCdEf بفرست.")

  raise ValueError("یوزرنیم، آیدی عددی یا لینک دعوت خصوصی کانال را بفرست.")


def channel_id_from_message_link(text: str):
  """Extract a Bot API chat identifier from a Telegram message link."""
  value = text.strip()
  match = re.search(
    r"https?://(?:www\.)?(?:t\.me|telegram\.me)/(?:s/)?([^/\s]+)/([0-9]+)(?:[/?#]|$)",
    value,
    flags=re.IGNORECASE,
  )

  if not match: return None

  peer = match.group(1)
  if peer == "c":
    private_match = re.search(
      r"https?://(?:www\.)?(?:t\.me|telegram\.me)/c/([0-9]+)/([0-9]+)(?:[/?#]|$)",
      value,
      flags=re.IGNORECASE,
    )

    if not private_match: return None
    return f"-100{private_match.group(1)}"

  if re.fullmatch(r"[A-Za-z0-9_]{5,32}", peer): return f"@{peer}"

  return None

def channel_default_link(chat_id: str, chat_username: str | None):
  if chat_username: return f"https://t.me/{chat_username.lstrip('@')}"
  if chat_id.startswith("@"): return f"https://t.me/{chat_id[1:]}"
  return None

_utf16_units = lambda value: (len(value.encode("utf-16-le")) // 2)

def _utf16_to_char_index(value: str, units: int) -> int:
  if units <= 0: return 0
  
  used = 0
  for index, char in enumerate(value):
    used += _utf16_units(char)
    if used > units: return index
    if used == units: return index + 1

  return len(value)

def _entity_char_ranges(text: str, entities: list[dict[str, object]] | None):
  ranges: list[dict[str, object]] = []
  for entity in entities or []:
    try:
      start_units = int(entity.get("offset", 0))
      length_units = int(entity.get("length", 0))
    except (TypeError, ValueError):
      continue

    if length_units <= 0: continue

    start = _utf16_to_char_index(text, start_units)
    end = _utf16_to_char_index(text, start_units + length_units)
    if start >= end: continue

    copied = dict(entity)
    copied["_start"] = start
    copied["_end"] = end
    ranges.append(copied)

  return ranges

def _wrap_rich_text(entity: dict[str, object], inner: object, plain: str):
  entity_type = str(entity.get("type") or "")
  if entity_type in {"bold", "italic", "underline", "strikethrough", "spoiler", "code"}:
    return {"type": entity_type, "text": inner}

  if entity_type == "custom_emoji":
    custom_emoji_id = entity.get("custom_emoji_id")
    if custom_emoji_id:
      return {
        "type": "custom_emoji",
        "custom_emoji_id": str(custom_emoji_id),
        "alternative_text": plain,
      }

  if entity_type == "text_link":
    url = entity.get("url")
    if url:
      return {"type": "url", "text": inner, "url": str(url)}

  if entity_type == "url":
    return {"type": "url", "text": inner, "url": plain}

  if entity_type == "text_mention":
    user = entity.get("user")
    if isinstance(user, dict):
      return {"type": "text_mention", "text": inner, "user": user}

  if entity_type == "mention":
    return {"type": "mention", "text": inner, "username": plain.lstrip("@")}

  if entity_type == "hashtag":
    return {"type": "hashtag", "text": inner, "hashtag": plain.lstrip("#")}

  if entity_type == "cashtag":
    return {"type": "cashtag", "text": inner, "cashtag": plain.lstrip("$")}

  if entity_type == "bot_command":
    return {"type": "bot_command", "text": inner, "bot_command": plain}

  if entity_type == "email":
    return {"type": "email_address", "text": inner, "email_address": plain}

  if entity_type == "phone_number":
    return {"type": "phone_number", "text": inner, "phone_number": plain}

  return inner

def _rich_text_from_ranges(text: str, ranges: list[dict[str, object]], start: int, end: int):
  relevant = [
    r for r in ranges
    if int(r.get("_start", -1)) >= start and int(r.get("_end", -1)) <= end
  ]

  if not relevant:return text[start:end]

  parts: list[object] = []
  pos = start

  # Outer entities first; nested entities are handled recursively.
  ordered = sorted(
    relevant,
    key=lambda r: (int(r.get("_start", 0)), -(int(r.get("_end", 0)) - int(r.get("_start", 0)))),
  )

  while pos < end:
    candidate = None
    for entity in ordered:
      entity_start = int(entity.get("_start", 0))
      entity_end = int(entity.get("_end", 0))

      if entity_start < pos or entity_end <= entity_start: continue
      if entity_start >= end: break

      candidate = entity
      break

    if candidate is None:
      parts.append(text[pos:end])
      break

    entity_start = int(candidate["_start"])
    entity_end = int(candidate["_end"])
    if entity_start > pos:
      parts.append(text[pos:entity_start])

    inner_ranges = [
      r for r in relevant
      if r is not candidate
      and int(r.get("_start", 0)) >= entity_start
      and int(r.get("_end", 0)) <= entity_end
    ]

    plain = text[entity_start:entity_end]
    inner = _rich_text_from_ranges(text, inner_ranges, entity_start, entity_end)
    parts.append(_wrap_rich_text(candidate, inner, plain))
    pos = entity_end

  compact = [part for part in parts if part != ""]

  if not compact: return ""
  if len(compact) == 1: return compact[0]

  return compact

def _strip_bot_mention_with_offset(text: str, bot_username: str | None = None):
  value = text.strip()
  leading_trim = len(text) - len(text.lstrip())
  if bot_username:
    pattern = MENTION_RE_TEMPLATE.format(username=re.escape(bot_username.lstrip("@")))
    match = re.match(pattern, value, flags=re.IGNORECASE)
    if match:
      stripped = value[match.end():].strip()
      """
      " Good enough for normal Telegram inline/guest messages: entities are shifted
      " by the removed leading mention and whitespace.
      """
      return stripped, leading_trim + match.end() + (len(value[match.end():]) - len(value[match.end():].lstrip()))

  return value, leading_trim

def apply_message_entities_to_paragraphs(blocks: list[dict[str, object]], original_text: str, entities: list[dict[str, object]] | None, bot_username: str | None = None):
  """Apply Telegram MessageEntity formatting to paragraph rich blocks.

  Mathematical blocks remain untouched. Paragraph blocks get RichText objects
  so bold/italic/code/links/custom emoji from the user's original message are
  transferred to the outgoing Rich Message.
  """
  if not entities: return blocks

  source_text, source_offset = _strip_bot_mention_with_offset(original_text, bot_username)
  ranges = _entity_char_ranges(original_text, entities)
  result: list[dict[str, object]] = []
  search_from = 0

  for block in blocks:
    if block.get("type") != "paragraph" or not isinstance(block.get("text"), str):
      result.append(block)
      continue

    paragraph = str(block["text"])
    found = source_text.find(paragraph, search_from)
    if found < 0:
      """
      " If parsing trimmed or merged lines, keep plain text rather than risking
      " wrong offsets.
      """
      result.append(block)
      continue

    abs_start = source_offset + found
    abs_end = abs_start + len(paragraph)
    rich_text = _rich_text_from_ranges(original_text, ranges, abs_start, abs_end)
    updated = dict(block)
    updated["text"] = rich_text
    result.append(updated)
    search_from = found + len(paragraph)

  return result


def parse_rich_blocks_with_entities(text: str, entities: list[dict[str, object]] | None = None, bot_username: str | None = None):
  blocks = parse_rich_blocks(text, bot_username)
  return apply_message_entities_to_paragraphs(blocks, text, entities, bot_username)
