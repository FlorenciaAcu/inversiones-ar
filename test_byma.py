import asyncio, httpx

YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

async def test():
    for ticker in ["SPY.BA", "QQQ.BA", "AL30.BA", "GGAL.BA"]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        async with httpx.AsyncClient(timeout=12, headers=YF_HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            data = r.json()
            closes = [x for x in (data["chart"]["result"][0]["indicators"]["quote"][0].get("close") or []) if x is not None]
            precio = closes[-1] if closes else None
            print(f"{ticker}: ${precio:,.0f}" if precio else f"{ticker}: sin datos")

asyncio.run(test())
