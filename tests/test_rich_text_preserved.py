from app.utils import has_math_block, parse_rich_blocks

def test_plain_text_is_preserved_before_latex():
  raw = "@LatexRM_bot میو\n\n \\displaystyle\\sum_{i=1}^{10} t_i"
  blocks = parse_rich_blocks(raw, "LatexRM_bot")
  assert blocks == [
    {"type": "paragraph", "text": "میو"},
    {
      "type": "mathematical_expression",
      "expression": r"\displaystyle\sum_{i=1}^{10} t_i",
    },
  ]
  assert has_math_block(blocks) is True


def test_plain_text_around_compact_equation_is_preserved():
  blocks = parse_rich_blocks("energy E=mc^2 is famous")
  assert blocks == [
    {"type": "paragraph", "text": "energy"},
    {"type": "mathematical_expression", "expression": "E=mc^2"},
    {"type": "paragraph", "text": "is famous"},
  ]


def test_plain_message_has_no_math_block():
  blocks = parse_rich_blocks("میو")
  assert blocks == [{"type": "paragraph", "text": "میو"}]
  assert has_math_block(blocks) is False


def test_explicit_wrapper_keeps_surrounding_text():
  blocks = parse_rich_blocks("before $$x^2+y^2$$ after")
  assert blocks == [
    {"type": "paragraph", "text": "before"},
    {"type": "mathematical_expression", "expression": "x^2+y^2"},
    {"type": "paragraph", "text": "after"},
  ]
