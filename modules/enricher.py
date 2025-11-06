"""
ماژول غنی‌سازی داده‌ها با Failover بین Birdeye و Dexscreener،
در صورت عدم نتیجه: رشته خالی بجای ارور، با لاگ فشرده.
"""

import httpx
import os
import asyncio
import logging
from httpx import ReadTimeout, ConnectError

logger = logging.getLogger(__name__)

BIRDEYE_API = os.getenv("EXTERNAL_API_ENDPOINT")
BIRDEYE_KEY = os.getenv("EXTERNAL_API_KEY")

DEX_API = os.getenv("DEX_API_ENDPOINT")
DEX_KEY = os.getenv("DEX_API_KEY")

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
SLEEP_RATE = 0.5

async def _query_birdeye(symbol, network, client):
    """تماس با Birdeye API با Retry Logic"""
    params = {"symbol": symbol, "chain": network}
    headers = {"Authorization": f"Bearer {BIRDEYE_KEY}"} if BIRDEYE_KEY else {}
    
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
            
            elif r.status_code == 429:
                await asyncio.sleep(1)
            else:
                logger.warning(f"BIRDEYE HTTP {r.status_code}: {symbol}-{network}")
                break 
                
    except (ReadTimeout, ConnectError) as e:
        logger.warning(f"BIRDEYE NetErr: {symbol}-{network}: {type(e).__name__}")
    except Exception as e:
        logger.error(f"BIRDEYE UnexpErr: {symbol}-{network}: {e}", exc_info=False)
        
    return None

async def _query_dexscreener(symbol, network, client):
    """تماس با Dexscreener API با Retry Logic"""
    params = {"symbol": symbol, "chain": network}
    headers = {"Authorization": f"Bearer {DEX_KEY}"} if DEX_KEY else {}
    
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

            elif r.status_code == 429:
                await asyncio.sleep(1)
            else:
                logger.warning(f"DEXSCREEN HTTP {r.status_code}: {symbol}-{network}")
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
    
    addr = await _query_dexscreener(symbol_clean, network_query, http_client)
    if addr:
        return addr
    
    logger.debug(f"FAIL: {symbol}-{network} NO ADDRESS")
    return ""

async def enrich_top_lists(top_sol: list, top_bnb: list) -> tuple[list, list]:
    """لیست‌های تاپ ۵ را با آدرس قرارداد غنی‌سازی می‌کند"""
    async with httpx.AsyncClient() as client:
        enriched_sol, enriched_bnb = [], []
        
        tasks_sol = []
        for symbol, count in top_sol:
            tasks_sol.append(get_contract_address(symbol, 'SOL', client))
        
        results_sol = await asyncio.gather(*tasks_sol)
        enriched_sol = [
            (top_sol[i][0], top_sol[i][1], addr or "") 
            for i, addr in enumerate(results_sol)
        ]
        
        await asyncio.sleep(SLEEP_RATE) 
        
        tasks_bnb = []
        for symbol, count in top_bnb:
            tasks_bnb.append(get_contract_address(symbol, 'BNB', client))
            
        results_bnb = await asyncio.gather(*tasks_bnb)
        enriched_bnb = [
            (top_bnb[i][0], top_bnb[i][1], addr or "") 
            for i, addr in enumerate(results_bnb)
        ]

        logger.info(f"Enrich: {len(enriched_sol)} SOL, {len(enriched_bnb)} BNB done")
        return enriched_sol, enriched_bnb