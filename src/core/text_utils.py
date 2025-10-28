from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

# HTML xuống dòng
_RE_BR = re.compile(r"<br\s*/?>", re.I)

# \text{...} của LaTeX
_RE_TEX_TEXT = re.compile(r"\\text\{(.*?)\}")

# Định danh ngôn ngữ sau ```lang\n
_RE_CODE_LANG = re.compile(r"```[\w\-]+\n")

# LaTeX -> ký hiệu
_LATEX_SYMBOLS: Dict[str, str] = {
    r"\\rightarrow": "→",
    r"\\leftrightarrow": "↔",
    r"\\rightleftharpoons": "⇌",
    r"\\longrightarrow": "⟶",
    r"\\to": "→",
    r"\\cdot": "·",
    r"\\times": "×",
    r"\\uparrow": "↑",
    r"\\downarrow": "↓",
    r"\\Delta": "Δ",
    r"\\nabla": "∇",
    r"\\geq": "≥",
    r"\\leq": "≤",
    r"\\pm": "±",
    r"\\neq": "≠",
    r"\\approx": "≈",
    # Hy Lạp thường gặp trong hoá
    r"\\alpha": "α",
    r"\\beta": "β",
    r"\\gamma": "γ",
    r"\\delta": "δ",
    r"\\theta": "θ",
    r"\\lambda": "λ",
    r"\\pi": "π",
    r"\\sigma": "σ",
    r"\\omega": "ω",
    r"\\Omega": "Ω",
}

# Chỉ số trên/dưới
_SUPERS = str.maketrans("0123456789+-()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾")
_SUBS   = str.maketrans("0123456789()",   "₀₁₂₃₄₅₆₇₈₉₍₎")

# ^{...}, ^x ; _{...}, _x
_RE_SUPER_CURLY = re.compile(r"\^\{([^}]*)\}")
_RE_SUPER_SIMPLE = re.compile(r"\^([0-9+\-\(\)])")
_RE_SUB_CURLY = re.compile(r"_\{([^}]*)\}")
_RE_SUB_SIMPLE = re.compile(r"_([0-9\(\)])")

# Vá lỗi dính dấu/không xuống dòng
_RE_AFTER_PUNCT = re.compile(r"([.,:;?!])([^\s\n])")
_RE_DOT_CAP = re.compile(r"([^\s])\.([A-ZÀ-Ỹ])")

# Dàn trang đề thi
_RE_SECTION_HEAD = re.compile(r"(?<!^)\s*(?=(?:[IVXLC]+\.)(?:\s|$))", re.M)  
_RE_QUESTION = re.compile(r"\s*(?=(Câu\s*\d+\s*:))", re.I)                   
_RE_CHOICES = re.compile(r"\s(?=([A-D])\.\s)")                              

# Khoảng trắng thừa trước xuống dòng
_RE_WS_BEFORE_NL = re.compile(r"[ \t]+\n")
_RE_MULTI_NL = re.compile(r"\n{3,}")

# 2) Các hàm hạt nhân
def replace_latex_symbols(text: str) -> str:
    """Thay LaTeX về ký hiệu Unicode thân thiện."""
    for pattern, repl in _LATEX_SYMBOLS.items():
        text = re.sub(pattern, repl, text)
    return text

def convert_supersubs(text: str) -> str:
    """Chuyển ^{...}, ^x, _{...}, _x về chữ số trên/dưới."""
    # Superscript
    text = _RE_SUPER_CURLY.sub(lambda m: m.group(1).translate(_SUPERS), text)
    text = _RE_SUPER_SIMPLE.sub(lambda m: m.group(1).translate(_SUPERS), text)
    # Subscript
    text = _RE_SUB_CURLY.sub(lambda m: m.group(1).translate(_SUBS), text)
    text = _RE_SUB_SIMPLE.sub(lambda m: m.group(1).translate(_SUBS), text)
    return text

def sanitize_markdown(text: str) -> str:
    """Làm sạch markdown rác: <br>, ```lang, ** trôi nổi, \\text{..}, dấu $."""
    text = _RE_BR.sub("\n", text)
    text = _RE_TEX_TEXT.sub(r"\1", text)
    text = text.replace("$", "")
    text = _RE_CODE_LANG.sub("```\n", text)
    # Xoá **/* đơn độc (không ôm chữ)
    text = re.sub(r"(?<!\S)\*{1,2}(?!\S)", "", text)
    return text

def fix_spacing(text: str) -> str:
    """Vá lỗi dính dấu câu & chữ hoa sau dấu chấm."""
    text = _RE_AFTER_PUNCT.sub(r"\1 \2", text)
    text = _RE_DOT_CAP.sub(r"\1. \2", text)
    return text

def apply_exam_layout(text: str) -> str:
    """Dàn trang đề thi: tách mục, câu hỏi, phương án; làm sạch dòng trống."""
    text = _RE_SECTION_HEAD.sub("\n\n", text.strip())
    text = _RE_QUESTION.sub(r"\n\n\1 ", text)
    text = _RE_CHOICES.sub(r"\n\1. ", text)
    text = _RE_WS_BEFORE_NL.sub("\n", text)
    text = _RE_MULTI_NL.sub("\n\n", text)
    return text

def normalize_arrows(text: str) -> str:
    """Thêm khoảng trắng quanh mũi tên phản ứng để dễ đọc."""
    text = re.sub(r"([A-Za-z0-9₀-₉⁰-⁹\)])→", r"\1 → ", text)
    text = re.sub(r"→([A-Za-z0-9₀-₉⁰-⁹\()])", r" → \1", text)
    return text

# -----------------------------
# 3) Hàm tổng hợp cho UI
# -----------------------------

def cleanup_response(
    text: str,
    *,
    do_symbols: bool = True,
    do_supersubs: bool = True,
    do_sanitize_md: bool = True,
    do_fix_spacing: bool = True,
    do_exam_layout: bool = True,
    do_arrow_space: bool = True,
) -> str:
    """
    Làm sạch + chuẩn hoá văn bản cho ChemA.
    Lưu ý: KHÔNG strip toàn chuỗi để không phá streaming.
    """
    if not text:
        return text

    if do_sanitize_md:
        text = sanitize_markdown(text)
    if do_symbols:
        text = replace_latex_symbols(text)
    if do_supersubs:
        text = convert_supersubs(text)
    if do_fix_spacing:
        text = fix_spacing(text)
    if do_exam_layout:
        text = apply_exam_layout(text)
    if do_arrow_space:
        text = normalize_arrows(text)

    # Chuẩn hoá tab -> space, giữ nguyên newline để stream đẹp
    return text.replace("\t", " ")

# -----------------------------
# 4) Tách câu hỏi trắc nghiệm
# -----------------------------

@dataclass
class Question:
    index: int
    stem: str
    choices: Dict[str, str]  # {"A": "...", "B": "...", ...}

_RE_SPLIT_Q = re.compile(r"(?:^|\n)Câu\s*(\d+)\s*:\s*(.*?)(?=\nCâu\s*\d+\s*:|\Z)", re.I | re.S)
_RE_SPLIT_CHOICES = re.compile(r"\n([A-D])\.\s+(.*?)(?=\n[A-D]\.\s+|\Z)", re.S)

def split_questions(text: str) -> List[Question]:
    """
    Từ khối văn bản (đã cleanup_layout), tách thành danh sách Question.
    Phù hợp để render UI Radio cho từng câu trong Streamlit.
    """
    qs: List[Question] = []
    for m in _RE_SPLIT_Q.finditer(text):
        idx = int(m.group(1))
        block = m.group(2).strip()
        # stem: phần trước lựa chọn đầu tiên
        parts = _RE_SPLIT_CHOICES.split("\n" + block)
        stem = parts[0].strip()
        choices: Dict[str, str] = {}
        for i in range(1, len(parts), 3):
            letter = parts[i].strip()
            content = parts[i + 1].strip()
            choices[letter] = content
        qs.append(Question(index=idx, stem=stem, choices=choices))
    return qs

# để test thôi
# if __name__ == "__main__":
#     raw = ("I. TRẮC NGHIỆM (4,0 điểm)- Chọn đáp án đúng nhất cho mỗi câu sau:\n"
#            "Câu 1: Chất nào sau đây là chất béo no, ở trạng thái rắn trong điều kiện thường? "
#            "A. Triolein, (C17H33COO)3C3H5. B. Trilinolein, (C17H31COO)3C3H5. "
#            "C. Tristearin, (C17H35COO)3C3H5. D. Glyceryl triacrylat,(CH2=CHCOO)3C3H5.\n"
#            "Câu 2: Khi thủy phân bất kỳ chất béo nào trongmôi trường kiềm(phản ứng xà phòng hóa),"
#            "sản phẩm thu được luôn có: A. Muối của axit béo và etylen glicol. "
#            "B. Axit béo và glixerol.C. Muối của axit béo và glixerol. D. Axit béo và ancol etylic.\n"
#            "Fe^3+ + 3OH^- -> Fe(OH)_3↓ <br> H_2SO_4"
#           )
#     clean = cleanup_response(raw)
#     print(clean)
#     for q in split_questions(clean):
#         print(f"\n[Câu {q.index}] {q.stem}")
#         for k, v in q.choices.items():
#             print(f"  {k}. {v}")
