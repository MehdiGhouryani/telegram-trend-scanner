"""
ماژول فرمت‌دهی پیام خروجی با نمایش سطر خالی بجای آدرس ناموجود، و لاگ هدفمند.
"""
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def format_output_message(enriched_sol: list, enriched_bnb: list) -> str:
    """
    خروجی: پیام تلگرام (markdown). اگر آدرس نبود، فقط یک خط فاصله زیر توکن/تکرار.
    """
    lines = []
    # رفع خطا: استفاده از زمان آگاه از منطقه زمانی (Timezone-Aware)
    timestamp = datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')
    any_data = False

    if enriched_sol:
        lines.append("🏆 **Top 5 Trending - $SOL** 🏆")
        lines.append(f"_(Updated: {timestamp})_\n")
        for idx, (symbol, count, address) in enumerate(enriched_sol, 1):
            lines.append(f"{idx}. **{symbol}** (تکرار: {count})")
            lines.append(f"   `{address}`\n" if address else "   \n")
            any_data = True
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if enriched_bnb:
        lines.append("🔥 **Top 5 Trending - $BNB** 🔥")
        lines.append(f"_(Updated: {timestamp})_\n")
        for idx, (symbol, count, address) in enumerate(enriched_bnb, 1):
            lines.append(f"{idx}. **{symbol}** (تکرار: {count})")
            lines.append(f"   `{address}`\n" if address else "   \n")
            any_data = True
    if not any_data:
        logger.info("Formatter: No data for output.")
        return ''
    msg = '\n'.join(lines)
    logger.debug(f"Formatter: MessageLen={len(msg)}")
    return msg