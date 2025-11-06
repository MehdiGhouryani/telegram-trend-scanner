"""
ماژول تحلیل فرکانس و شناسایی توکن‌های پرتکرار
"""

from collections import Counter
import logging

logger = logging.getLogger(__name__)

def analyze_frequency(sol_tokens: list, bnb_tokens: list) -> tuple[list, list]:
    """
    دو لیست خام از توکن‌ها را گرفته و لیست تاپ ۵ پرتکرار هر کدام را برمی‌گرداند.
    
    Args:
        sol_tokens: لیست نمادهای توکن سولانا
        bnb_tokens: لیست نمادهای توکن بایننس
        
    Returns:
        tuple: (top_sol, top_bnb) - دو لیست از (symbol, count)
    """
    # شمارش فرکانس توکن‌ها
    sol_counter = Counter(sol_tokens)
    bnb_counter = Counter(bnb_tokens)
    
    # استخراج ۵ توکن برتر
    top_sol = sol_counter.most_common(5)
    top_bnb = bnb_counter.most_common(5)
    
    logger.debug(
        f"Analyzer: Top SOL={len(top_sol)}, Top BNB={len(top_bnb)}"
    )
    
    return top_sol, top_bnb
