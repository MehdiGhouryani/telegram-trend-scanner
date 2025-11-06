"""
ماژول غنی‌سازی داده‌ها با Failover بین Birdeye و Dexscreener،
در صورت عدم نتیجه: رشته خالی بجای ارور، با لاگ فشرده.
"""

import httpx
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

BIRDEYE_API = os.getenv("EXTERNAL_API_ENDPOINT")     # مثلاً https://api.birdeye.so/defi/tokenlist
BIRDEYE_KEY = os.getenv("EXTERNAL_API_KEY")

DEX_API = os.getenv("DEX_API_ENDPOINT")              # مثلاً https://api.dexscreener.com/latest/dex/tokens
DEX_KEY = os.getenv("DEX_API_KEY")

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
SLEEP_RATE = 0.5

async def _query_birdeye(symbol, network, client):
    """تماس با Birdeye API"""
    params = {"symbol": symbol, "chain": network}
    headers = {"Authorization": f"Bearer {BIRDEYE_KEY}"} if BIRDEYE_KEY else {}
    try:
        for attempt in range(MAX_RETRIES):
            r = await client.get(BIRDEYE_API, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                json_ = r.json()
                results = json_.get("data", [])
                if results:
                    sorted_ = sorted(results, key=lambda x: x.get("volume_24h", 0), reverse=True)
                    addr = sorted_[0].get("address")
                    if addr:
                        logger.info(f"BIRDEYE: {symbol}-{network} {addr[:8]}... OK")
                        return addr
                logger.info(f"BIRDEYE: {symbol}-{network} NotFound")
                return None
            elif r.status_code == 429:
                await asyncio.sleep(1)
            else:
                break
    except Exception as e:
        logger.warning(f"BIRDEYE ERR: {symbol}-{network}: {e}")
    return None

async def _query_dexscreener(symbol, network, client):
    """تماس با Dexscreener API - فرض ساختار مشابه"""
    params = {"symbol": symbol, "chain": network}
    headers = {"Authorization": f"Bearer {DEX_KEY}"} if DEX_KEY else {}
    try:
        for attempt in range(MAX_RETRIES):
            r = await client.get(DEX_API, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                json_ = r.json()
                results = json_.get("pairs", [])
                if results:
                    sorted_ = sorted(results, key=lambda x: x.get("volume24hUSD", 0), reverse=True)
                    addr = sorted_[0].get("baseToken", {}).get("address")
                    if addr:
                        logger.info(f"DEXSCREEN: {symbol}-{network} {addr[:8]}... OK")
                        return addr
                logger.info(f"DEXSCREEN: {symbol}-{network} NotFound")
                return None
            elif r.status_code == 429:
                await asyncio.sleep(1)
            else:
                break
    except Exception as e:
        logger.warning(f"DEXSCREEN ERR: {symbol}-{network}: {e}")
    return None

async def get_contract_address(symbol: str, network: str, http_client: httpx.AsyncClient) -> str:
    """
    تلاش با هر دو API و بازگرداندن address یا "" اگر پیدا نشود.
    """
    symbol_clean = symbol.replace("$", "").replace("#", "").strip().upper()
    network_map = {"SOL": "solana", "BNB": "bsc"}
    network_query = network_map.get(network.upper(), network.lower())
    
    # ابتدا با Birdeye
    addr = await _query_birdeye(symbol_clean, network_query, http_client)
    if addr:
        return addr
    # سپس با Dexscreener
    addr = await _query_dexscreener(symbol_clean, network_query, http_client)
    if addr:
        return addr
    # هیچکدام موفق نبود، رشته خالی
    logger.info(f"FAIL: {symbol}-{network} NO ADDRESS")
    return ""

async def enrich_top_lists(top_sol: list, top_bnb: list) -> tuple[list, list]:
    """
    لیست تاپ ۵ را با آدرس قرارداد (در صورت موفقیت) enrich می‌کند. اگر پیدا نشود، رشته خالی بجای آدرس.
    """
    async with httpx.AsyncClient() as client:
        enriched_sol, enriched_bnb = [], []
        for symbol, count in top_sol:
            addr = await get_contract_address(symbol, 'SOL', client)
            enriched_sol.append((symbol, count, addr or ""))
            await asyncio.sleep(SLEEP_RATE)
        for symbol, count in top_bnb:
            addr = await get_contract_address(symbol, 'BNB', client)
            enriched_bnb.append((symbol, count, addr or ""))
            await asyncio.sleep(SLEEP_RATE)
        logger.info(f"Enrich: {len(enriched_sol)} SOL, {len(enriched_bnb)} BNB done")
        return enriched_sol, enriched_bnb
