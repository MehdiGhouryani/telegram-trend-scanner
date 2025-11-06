"""
ماژول استخراج و پارس توکن‌های SOL و BNB از پیام‌های تلگرام
"""

import re
import logging

logger = logging.getLogger(__name__)

def parse_messages(messages: list) -> tuple[list, list]:
    """
    لیستی از آبجکت‌های پیام تلثون را گرفته و توکن‌های SOL و BNB را در دو لیست مجزا برمی‌گرداند.
    
    Args:
        messages: لیست پیام‌های دریافتی از تلگرام
        
    Returns:
        tuple: (sol_tokens, bnb_tokens) - دو لیست از نمادهای توکن
    """
    sol_tokens = []
    bnb_tokens = []
    
    # الگوهای Regex برای شناسایی بلاک‌های Heatmap
    bnb_block_pattern = r"Trending.*\$BNB Heatmap(.*?)(?:Updated every|$)"
    sol_block_pattern = r"Trending.*\$SOL Heatmap(.*?)(?:Updated every|$)"
    
    # الگوی استخراج نماد توکن (پشتیبانی از انگلیسی، چینی و اعداد)
    token_pattern = re.compile(
        r"\d+\.\s+([$#]?[A-Za-z0-9\u4e00-\u9fa5]+)",
        re.UNICODE
    )
    
    parsed_count = 0
    
    for message in messages:
        text = getattr(message, "text", None)
        
        # بررسی معتبر بودن متن پیام
        if not isinstance(text, str) or not text.strip():
            continue
        
        # استخراج بلاک‌های BNB
        for bnb_block in re.findall(bnb_block_pattern, text, re.DOTALL):
            tokens = token_pattern.findall(bnb_block)
            normalized_tokens = [t.strip() for t in tokens if t.strip()]
            bnb_tokens.extend(normalized_tokens)
            if normalized_tokens:
                parsed_count += 1
        
        # استخراج بلاک‌های SOL
        for sol_block in re.findall(sol_block_pattern, text, re.DOTALL):
            tokens = token_pattern.findall(sol_block)
            normalized_tokens = [t.strip() for t in tokens if t.strip()]
            sol_tokens.extend(normalized_tokens)
            if normalized_tokens:
                parsed_count += 1
    
    logger.debug(f"Parser: {parsed_count} بلاک Heatmap پردازش شد")
    
    return sol_tokens, bnb_tokens
