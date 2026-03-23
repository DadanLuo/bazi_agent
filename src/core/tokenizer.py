# src/core/tokenizer.py
"""Token 估算工具 — 替代各处 len(text)//3 的错误估算"""


def estimate_tokens(text: str) -> int:
    """
    估算 token 数量
    中文 ~1.5 字符/token，ASCII ~4 字符/token
    """
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    ascii_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + ascii_chars / 4)
