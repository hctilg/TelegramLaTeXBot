from app.utils import is_latex_expression, normalize_expression, parse_channel_input, validate_expression

def test_normalize_guest_expression():
  raw = r"@LaTeXRm_Bot \displaystyle\sum_{i=1}^{10} t_i"
  assert normalize_expression(raw, "LaTeXRm_Bot") == r"\displaystyle\sum_{i=1}^{10} t_i"

def test_strip_math_wrappers():
  assert normalize_expression(r"$$x^2+y^2$$") == r"x^2+y^2"
  assert normalize_expression(r"<tg-math-block>E=mc^2</tg-math-block>") == "E=mc^2"

def test_validate_expression():
  assert validate_expression("x^2")[0] is True
  assert validate_expression("")[0] is False

def test_parse_channel_input():
  assert parse_channel_input("@example_channel") == ("@example_channel", None)
  assert parse_channel_input("-1001234567890 | https://t.me/+abc") == (
    "-1001234567890",
    "https://t.me/+abc",
  )

def test_latex_detection_accepts_real_expressions():
  assert is_latex_expression(r"\displaystyle\sum_{i=1}^{10} t_i") is True
  assert is_latex_expression(r"$$E=mc^2$$") is True
  assert is_latex_expression("E=mc^2") is True
  assert is_latex_expression("x+y") is True
  assert is_latex_expression(r"@LaTeXRm_Bot \frac{1}{2}", "LaTeXRm_Bot") is True

def test_latex_detection_rejects_plain_text():
  assert is_latex_expression("سلام خوبی؟") is False
  assert is_latex_expression("hello world") is False
  assert is_latex_expression("this is normal text") is False
  assert is_latex_expression("@LaTeXRm_Bot hello world", "LaTeXRm_Bot") is False

def test_extract_only_latex_from_mixed_guest_text():
  from app.utils import extract_latex_expression
  raw = "@LatexRM_bot میو\n\n \\displaystyle\\sum_{i=1}^{10} t_i"
  assert extract_latex_expression(raw, "LatexRM_bot") == r"\displaystyle\sum_{i=1}^{10} t_i"

def test_extract_latex_after_plain_text_same_line():
  from app.utils import extract_latex_expression
  raw = r"@LatexRM_bot میو \displaystyle\sum_{i=1}^{10} t_i"
  assert extract_latex_expression(raw, "LatexRM_bot") == r"\displaystyle\sum_{i=1}^{10} t_i"

def test_extract_compact_equation_from_sentence():
  from app.utils import extract_latex_expression
  assert extract_latex_expression("render this E=mc^2") == "E=mc^2"

def test_extract_rejects_plain_text():
  from app.utils import extract_latex_expression
  assert extract_latex_expression("میو") == ""
