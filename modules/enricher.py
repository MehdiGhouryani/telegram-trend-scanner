"""
ماژول غنی‌سازی داده‌ها با Failover و تلاش مجدد هوشمند.
- Birdeye: تلاش مجدد برای خطاهای 429 و 5xx (مانند 521)
- Dexscreener: تلاش مجدد فقط برای 429
- لاگ‌نویسی هوشمند با ثبت پاسخ خطا از سرور.
"""

import httpx
import os
import asyncio
import logging
from httpx import ReadTimeout, ConnectError

logger = logging.getLogger(__name__)

# --- تنظیمات API ---
BIRDEYE_API = os.getenv("EXTERNAL_API_ENDPOINT")
BIRDEYE_KEY = os.getenv("EXTERNAL_API_KEY")
DEX_API = os.getenv("DEX_API_ENDPOINT")
DEX_KEY = os.getenv("DEX_API_KEY")

# --- تنظیمات تلاش مجدد ---
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
SLEEP_RATE = 0.5  # تاخیر بین فراخوانی‌های gather در enrich_top_lists

# کدهای وضعیتی که برای Birdeye منجر به تلاش مجدد می‌شوند (خطای سرور یا ریت لیمیت)
BIRDEYE_RETRY_STATUS_CODES = [429, 500, 502, 503, 504, 521]
BIRDEYE_RETRY_SLEEP_SECONDS = 3


def _get_response_snippet(response_text: str, length: int = 150) -> str:
    """یک قطعه فشرده و ایمن از متن پاسخ برای لاگ‌نویسی برمی‌گرداند."""
    if not response_text:
        return "[No Response Body]"
    return (response_text[:length].replace("\n", " ") + "...")


async def _query_birdeye(symbol, network, client):
    """تماس با Birdeye API با Retry Logic هوشمند برای 5xx و 429"""
    params = {"symbol": symbol, "chain": network}
    headers = {"Authorization": f"Bearer {BIRDEYE_KEY}"} if BIRDEYE_KEY else {}
    
    if not BIRDEYE_API:
        logger.error("BIRDEYE_API (EXTERNAL_API_ENDPOINT) در .env تنظیم نشده است.")
        return None

    try:
        for attempt in range(MAX_RETRIES):
            r = await client.get(
                BIRDEYE_API, 
                params=params, 
                headers=headers, 
                timeout=REQUEST_TIMEOUT
            )
            
            if r.status_code == 200:
                json_ = r.json()
                results = json_.get("data", [])
                if results:
                    sorted_ = sorted(
                        results, 
                        key=lambda x: x.get("volume_24h", 0), 
                        reverse=True
                    )
                    addr = sorted_[0].get("address")
                    if addr:
                        logger.info(f"BIRDEYE OK: {symbol}-{network} -> {addr[:8]}...")
                        return addr
                
                logger.debug(f"BIRDEYE NotFound: {symbol}-{network}")
                return None
            
            # منطق تلاش مجدد هوشمند (فقط Birdeye)
            elif r.status_code in BIRDEYE_RETRY_STATUS_CODES:
                snippet = _get_response_snippet(r.text)
                logger.warning(
                    f"BIRDEYE HTTP {r.status_code} (Retry {attempt+1}): "
                    f"{symbol}-{network} | Resp: {snippet} | "
                    f"Waiting {BIRDEYE_RETRY_SLEEP_SECONDS}s..."
                )
                await asyncio.sleep(BIRDEYE_RETRY_SLEEP_SECONDS)
            
            # خطاهای دیگر (مانند 400, 401, 404) که نباید دوباره تلاش شوند
            else:
                snippet = _get_response_snippet(r.text)
                logger.warning(
                    f"BIRDEYE HTTP {r.status_code} (No Retry): "
                    f"{symbol}-{network} | Resp: {snippet}"
                )
                break 
                
    except (ReadTimeout, ConnectError) as e:
        logger.warning(f"BIRDEYE NetErr: {symbol}-{network}: {type(e).__name__}")
    except Exception as e:
        logger.error(f"BIRDEYE UnexpErr: {symbol}-{network}: {e}", exc_info=False)
        
    return None

async def _query_dexscreener(symbol, network, client):
    """تماس با Dexscreener API با Retry Logic فقط برای 429"""
    params = {"symbol": symbol, "chain": network}
    headers = {"Authorization": f"Bearer {DEX_KEY}"} if DEX_KEY else {}
    
    if not DEX_API:
        logger.error("DEX_API (DEX_API_ENDPOINT) در .env تنظیم نشده است.")
        return None

    try:
        for attempt in range(MAX_RETRIES):
            r = await client.get(
                DEX_API, 
                params=params, 
                headers=headers, 
                timeout=REQUEST_TIMEOUT
            )
            
            if r.status_code == 200:
                json_ = r.json()
                results = json_.get("pairs", [])
                if results:
                    sorted_ = sorted(
                        results, 
                        key=lambda x: x.get("volume24hUSD", 0), 
                        reverse=True
                    )
                    addr = sorted_[0].get("baseToken", {}).get("address")
                    if addr:
                        logger.info(f"DEXSCREEN OK: {symbol}-{network} -> {addr[:8]}...")
                        return addr
                
                logger.debug(f"DEXSCREEN NotFound: {symbol}-{network}")
                return None

            # منطق تلاش مجدد (فقط Dexscreener)
            elif r.status_code == 429:
                snippet = _get_response_snippet(r.text)
                logger.warning(
                    f"DEXSCREEN HTTP 429 (Retry {attempt+1}): "
                    f"{symbol}-{network} | Resp: {snippet} | Waiting 1s..."
                )
                await asyncio.sleep(1)
            
            # خطاهای دیگر (404، 5xx و ...)
            else:
                snippet = _get_response_snippet(r.text)
                logger.warning(
                    f"DEXSCREEN HTTP {r.status_code} (No Retry): "
                    f"{symbol}-{network} | Resp: {snippet}"
                )
                break
                
    except (ReadTimeout, ConnectError) as e:
        logger.warning(f"DEXSCREEN NetErr: {symbol}-{network}: {type(e).__name__}")
    except Exception as e:
        logger.error(f"DEXSCREEN UnexpErr: {symbol}-{network}: {e}", exc_info=False)
        
    return None

async def get_contract_address(symbol: str, network: str, http_client: httpx.AsyncClient) -> str:
    """تلاش برای واکشی آدرس با Failover بین Birdeye و Dexscreener"""
    symbol_clean = symbol.replace("$", "").replace("#", "").strip().upper()
    network_map = {"SOL": "solana", "BNB": "bsc"}
    network_query = network_map.get(network.upper(), network.lower())
    
    addr = await _query_birdeye(symbol_clean, network_query, http_client)
    if addr:
        return addr
    
    # اگر Birdeye نشد (به هر دلیلی)، سراغ Dexscreener می‌رویم
    logger.debug(f"Birdeye failed for {symbol}-{network}, trying Dexscreener...")
    
    addr = await _query_dexscreener(symbol_clean, network_query, http_client)
    if addr:
        return addr
    
    logger.debug(f"FAIL: {symbol}-{network} NO ADDRESS (tried both APIs)")
    return ""

async def enrich_top_lists(top_sol: list, top_bnb: list) -> tuple[list, list]:
    """لیست‌های تاپ ۵ را با آدرس قرارداد غنی‌سازی می‌کند (با استفاده از asyncio.gather)"""
    async with httpx.AsyncClient() as client:
        enriched_sol, enriched_bnb = [], []
        
        # --- پردازش SOL ---
        tasks_sol = []
        for symbol, count in top_sol:
            tasks_sol.append(get_contract_address(symbol, 'SOL', client))
        
        results_sol = await asyncio.gather(*tasks_sol)
        enriched_sol = [
            (top_sol[i][0], top_sol[i][1], addr or "") 
            for i, addr in enumerate(results_sol)
        ]
        
        await asyncio.sleep(SLEEP_RATE)  # تاخیر کوتاه بین دسته‌های SOL و BNB
        
        # --- پردازش BNB ---
        tasks_bnb = []
        for symbol, count in top_bnb:
            tasks_bnb.append(get_contract_address(symbol, 'BNB', client))
            
        results_bnb = await asyncio.gather(*tasks_bnb)
        enriched_bnb = [
            (top_bnb[i][0], top_bnb[i][1], addr or "") 
            for i, addr in enumerate(results_bnb)
        ]

        logger.info(f"Enrich: {len(results_sol)} SOL, {len(results_bnb)} BNB tasks done")
        return enriched_sol, enriched_bnb