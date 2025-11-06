"""
ماژول فرمت‌دهی پیام خروجی (بازنویسی شده برای ارسال پیام‌های جداگانه)
"""
from datetime import datetime, UTC
import logging

logger = logging.getLogger(__name__)


def _format_single_chain(enriched_data: list, chain_name: str) -> str:
    """
    یک لیست غنی‌شده (برای یک زنجیره خاص) را گرفته و پیام آن را فرمت می‌کند.
    """
    if not enriched_data:
        logger.info(f"Formatter: No data for {chain_name}.")
        return ""

    lines = []
    
    # تنظیم هدر بر اساس نام زنجیره
    if chain_name.upper() == "SOL":
        lines.append("🏆 **Top 5 Trending - $SOL** 🏆\n")
    elif chain_name.upper() == "BNB":
        lines.append("🔥 **Top 5 Trending - $BNB** 🔥\n")

    # حذف خط timestamp و تعداد تکرار طبق درخواست
    for idx, (symbol, count, address) in enumerate(enriched_data, 1):
        lines.append(f"{idx}. **{symbol}**")
        lines.append(f"   `{address}`\n" if address else "   \n")
    
    msg = '\n'.join(lines)
    logger.debug(f"Formatter: MessageLen={len(msg)} for {chain_name}")
    # .strip() برای حذف هرگونه خط خالی اضافه در ابتدا یا انتها
    return msg.strip()


def format_output_message(enriched_sol: list, enriched_bnb: list) -> tuple[str, str]:
    """
    دو لیست غنی‌شده را گرفته و دو پیام مجزا (sol_message, bnb_message) برمی‌گرداند.
    """
    
    sol_message = _format_single_chain(enriched_sol, "SOL")
    bnb_message = _format_single_chain(enriched_bnb, "BNB")
    
    # بازگرداندن دو پیام به صورت مجزا
    return sol_message, bnb_message