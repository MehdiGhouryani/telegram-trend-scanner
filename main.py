"""
Telegram Trend Scanner Bot
اسکنر و تحلیلگر خودکار ترند توکن‌های کریپتو از کانال‌های تلگرام
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChannelPrivateError
from dotenv import load_dotenv

from modules.parser import parse_messages
from modules.analyzer import analyze_frequency
from modules.enricher import enrich_top_lists
from modules.formatter import format_output_message

# بارگذاری متغیرهای محیطی
load_dotenv()

# تنظیم سیستم لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# اعتبارسنجی و بارگذاری متغیرهای محیطی
def load_config():
    """بارگذاری و اعتبارسنجی تنظیمات از .env"""
    try:
        config = {
            'API_ID': int(os.getenv("API_ID")),
            'API_HASH': os.getenv("API_HASH"),
            'SESSION_NAME': os.getenv("SESSION_NAME", "trend_scanner"),
            'SOURCE_CHANNEL_ID': os.getenv("SOURCE_CHANNEL_ID"),
            'DEST_CHANNEL_ID': os.getenv("DESTINATION_CHANNEL_ID"),
            'LOOP_INTERVAL_SECONDS': int(os.getenv("LOOP_INTERVAL_SECONDS", 1800))
        }
        
        # بررسی وجود مقادیر ضروری
        if not config['API_HASH']:
            raise ValueError("API_HASH خالی است")
        if not config['SOURCE_CHANNEL_ID']:
            raise ValueError("SOURCE_CHANNEL_ID خالی است")
        if not config['DEST_CHANNEL_ID']:
            raise ValueError("DESTINATION_CHANNEL_ID خالی است")
        
        logger.info("✓ تنظیمات با موفقیت بارگذاری شد")
        return config
    
    except (ValueError, TypeError) as e:
        logger.error(f"✗ خطا در بارگذاری تنظیمات: {e}")
        exit(1)

async def process_trends(client, config):
    """
    پردازش اصلی: دریافت، تحلیل و انتشار ترندها
    """
    try:
        now = datetime.utcnow()
        since = now - timedelta(seconds=config['LOOP_INTERVAL_SECONDS'])
        
        logger.info(f"→ شروع اسکن پیام‌ها از {since.strftime('%H:%M:%S')} تا {now.strftime('%H:%M:%S')}")
        
        # دریافت پیام‌ها از کانال منبع
        messages = []
        async for msg in client.iter_messages(
            config['SOURCE_CHANNEL_ID'],
            limit=200
        ):
            if msg.date < since:
                break
            if msg.date >= since and getattr(msg, "text", None):
                messages.append(msg)
        
        if not messages:
            logger.warning("⚠ هیچ پیامی در این بازه زمانی یافت نشد")
            return
        
        logger.info(f"✓ {len(messages)} پیام دریافت شد")
        
        # گام ۱: استخراج توکن‌ها
        sol_tokens, bnb_tokens = parse_messages(messages)
        total_tokens = len(sol_tokens) + len(bnb_tokens)
        
        if total_tokens == 0:
            logger.warning("⚠ هیچ توکنی شناسایی نشد")
            return
        
        logger.info(f"✓ {len(sol_tokens)} توکن SOL و {len(bnb_tokens)} توکن BNB استخراج شد")
        
        # گام ۲: تحلیل فرکانس
        top_sol, top_bnb = analyze_frequency(sol_tokens, bnb_tokens)
        logger.info(f"✓ تحلیل فرکانس انجام شد")
        
        # گام ۳: غنی‌سازی با آدرس قرارداد
        logger.info("→ در حال واکشی آدرس قراردادها از API...")
        enriched_sol, enriched_bnb = await enrich_top_lists(top_sol, top_bnb)
        logger.info("✓ غنی‌سازی داده‌ها تکمیل شد")
        
        # گام ۴: ساخت پیام خروجی
        final_message = format_output_message(enriched_sol, enriched_bnb)
        
        if not final_message:
            logger.warning("⚠ پیام خروجی خالی است")
            return
        
        # ارسال به کانال مقصد
        await client.send_message(
            config['DEST_CHANNEL_ID'],
            final_message,
            parse_mode="md"
        )
        logger.info("✓ گزارش با موفقیت ارسال شد")
        
    except FloodWaitError as e:
        logger.error(f"✗ محدودیت تلگرام: باید {e.seconds} ثانیه صبر کنید")
        await asyncio.sleep(e.seconds)
    
    except ChannelPrivateError:
        logger.error("✗ دسترسی به کانال ممکن نیست (خصوصی یا بن شده)")
    
    except Exception as e:
        logger.error(f"✗ خطای غیرمنتظره: {e}", exc_info=True)

async def main():
    """حلقه اصلی برنامه"""
    config = load_config()
    
    # ایجاد کلاینت تلگرام
    client = TelegramClient(
        config['SESSION_NAME'],
        config['API_ID'],
        config['API_HASH']
    )
    
    try:
        await client.start()
        logger.info("=" * 50)
        logger.info("🤖 ربات اسکنر ترند تلگرام فعال شد")
        logger.info(f"⏱ بازه زمانی اسکن: هر {config['LOOP_INTERVAL_SECONDS']} ثانیه")
        logger.info("=" * 50)
        
        while True:
            await process_trends(client, config)
            logger.info(f"💤 در حالت انتظار برای {config['LOOP_INTERVAL_SECONDS']} ثانیه...\n")
            await asyncio.sleep(config['LOOP_INTERVAL_SECONDS'])
    
    except KeyboardInterrupt:
        logger.info("\n⏹ دریافت سیگنال توقف...")
    
    except Exception as e:
        logger.error(f"✗ خطای کلی برنامه: {e}", exc_info=True)
    
    finally:
        await client.disconnect()
        logger.info("👋 ربات با موفقیت خاموش شد")

if __name__ == "__main__":
    asyncio.run(main())
