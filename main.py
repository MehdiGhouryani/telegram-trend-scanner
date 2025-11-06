"""
Telegram Trend Scanner Bot
اسکنر و تحلیلگر خودکار ترند توکن‌های کریپتو از کانال‌های تلگرام
"""

# گام ۱: بارگذاری .env باید قبل از هر ایمپورت دیگری از ماژول‌ها انجام شود
# تا متغیرهای محیطی برای ماژول enricher در دسترس باشند
from dotenv import load_dotenv
load_dotenv()

import os
import sys
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta, UTC  # ایمپورت UTC برای رفع خطای زمان
from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChannelPrivateError

# اکنون ماژول‌ها ایمپورت می‌شوند
from modules.parser import parse_messages
from modules.analyzer import analyze_frequency
from modules.enricher import enrich_top_lists
from modules.formatter import format_output_message

logger = logging.getLogger(__name__)

LOG_FORMAT = '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'

def setup_logging():
    """راه‌اندازی سیستم لاگ چرخشی (۵ مگابایت) و لاگ کنسول"""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)
    
    try:
        file_handler = RotatingFileHandler(
            "scanner.log", 
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=1
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except PermissionError:
        print("Error: Permission denied to write log file 'scanner.log'.")
    except Exception as e:
        print(f"Error setting up file logger: {e}")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

def load_config():
    """بارگذاری و اعتبارسنجی تنظیمات از .env"""
    try:
        config = {
            'API_ID': int(os.getenv("API_ID")),
            'API_HASH': os.getenv("API_HASH"),
            'SESSION_NAME': os.getenv("SESSION_NAME", "trend_scanner"),
            'SOURCE_CHANNEL_ID': int(os.getenv("SOURCE_CHANNEL_ID")),
            'DEST_CHANNEL_ID': int(os.getenv("DESTINATION_CHANNEL_ID")),
            'LOOP_INTERVAL_SECONDS': int(os.getenv("LOOP_INTERVAL_SECONDS", 1800)),
            # اعلان ادمین همیشه فعال است و از .env خوانده نمی‌شود
        }
        
        if not config['API_HASH']:
            raise ValueError("API_HASH خالی است")
        
        logger.info("✓ تنظیمات با موفقیت بارگذاری شد")
        return config
    
    except (ValueError, TypeError) as e:
        logger.error(f"✗ خطا در بارگذاری تنظیمات: {e}")
        logger.error("!!! لطفاً مطمئن شوید API_ID, API_HASH, و ID کانال‌ها به درستی در فایل .env وارد شده‌اند.")
        exit(1)

async def notify_admin(client, message, config):
    """ارسال پیام وضعیت به ادمین (Saved Messages)"""
    # بررسی حذف شد، اعلان همیشه ارسال می‌شود
    try:
        await client.send_message('me', message, parse_mode='md')
    except Exception as e:
        logger.warning(f"Failed to send admin notification: {e}")

async def process_trends(client, config):
    """پردازش اصلی: دریافت، تحلیل و انتشار ترندها"""
    try:
        # رفع خطای مقایسه زمان: استفاده از زمان آگاه از منطقه زمانی
        now = datetime.now(UTC)
        since = now - timedelta(seconds=config['LOOP_INTERVAL_SECONDS'])
        
        logger.info(f"→ شروع اسکن پیام‌ها از {since.strftime('%H:%M:%S')}")
        await notify_admin(client, "🔍 چرخه اسکن جدید آغاز شد...", config)
        
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
            await notify_admin(client, "ℹ️ هیچ پیام جدیدی یافت نشد.", config)
            return
        
        logger.info(f"✓ {len(messages)} پیام دریافت شد")
        
        sol_tokens, bnb_tokens = parse_messages(messages)
        total_tokens = len(sol_tokens) + len(bnb_tokens)
        
        if total_tokens == 0:
            logger.warning("⚠ هیچ توکنی شناسایی نشد")
            await notify_admin(client, "ℹ️ هیچ توکنی در پیام‌ها شناسایی نشد.", config)
            return
        
        logger.info(f"✓ {len(sol_tokens)} توکن SOL و {len(bnb_tokens)} توکن BNB استخراج شد")
        
        top_sol, top_bnb = analyze_frequency(sol_tokens, bnb_tokens)
        logger.info(f"✓ تحلیل فرکانس انجام شد")
        
        logger.info("→ در حال واکشی آدرس قراردادها...")
        enriched_sol, enriched_bnb = await enrich_top_lists(top_sol, top_bnb)
        logger.info("✓ غنی‌سازی داده‌ها تکمیل شد")
        
        final_message = format_output_message(enriched_sol, enriched_bnb)
        
        if not final_message:
            logger.warning("⚠ پیام خروجی خالی است (داده‌ای برای نمایش نبود)")
            await notify_admin(client, "ℹ️ داده‌ای برای ساخت گزارش نهایی یافت نشد.", config)
            return
        
        await client.send_message(
            config['DEST_CHANNEL_ID'],
            final_message,
            parse_mode="md"
        )
        logger.info("✓ گزارش با موفقیت ارسال شد")
        await notify_admin(client, "✅ گزارش با موفقیت ارسال شد.", config)
        
    except FloodWaitError as e:
        logger.error(f"✗ محدودیت تلگرام: باید {e.seconds} ثانیه صبر کنید")
        await notify_admin(client, f"⏳ محدودیت تلگرام: {e.seconds} ثانیه صبر.", config)
        await asyncio.sleep(e.seconds)
    
    except ChannelPrivateError:
        logger.error("✗ دسترسی به کانال ممکن نیست (خصوصی یا بن شده)")
        await notify_admin(client, "❌ خطا: دسترسی به کانال (منبع یا مقصد) ممکن نیست.", config)
    
    except Exception as e:
        logger.error(f"✗ خطای غیرمنتظره: {e}", exc_info=True)
        await notify_admin(client, f"🆘 خطای غیرمنتظره:\n`{str(e)}`", config)

async def main():
    """حلقه اصلی برنامه"""
    setup_logging()
    config = load_config()
    
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
        # لاگ اعلان ادمین حذف شد چون اکنون همیشه فعال است
        logger.info("=" * 50)
        await notify_admin(client, "🤖 **ربات اسکنر ترند فعال شد**", config)
        
        while True:
            await process_trends(client, config)
            logger.info(f"💤 در حالت انتظار برای {config['LOOP_INTERVAL_SECONDS']} ثانیه...\n")
            await asyncio.sleep(config['LOOP_INTERVAL_SECONDS'])
    
    except KeyboardInterrupt:
        logger.info("\n⏹ دریافت سیگنال توقف...")
    
    except Exception as e:
        logger.error(f"✗ خطای کلی برنامه: {e}", exc_info=True)
        await notify_admin(client, f"🆘 **خطای مرگبار برنامه**:\n`{str(e)}`", config)
    
    finally:
        if client.is_connected():
            await notify_admin(client, "👋 ربات در حال خاموش شدن...", config)
            await client.disconnect()
        logger.info("👋 ربات با موفقیت خاموش شد")

if __name__ == "__main__":
    asyncio.run(main())