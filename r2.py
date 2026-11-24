import asyncio, sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width":1024,"height":1024})
        await pg.goto("file:///root/build/news-image24/news.html")
        await pg.wait_for_timeout(500)
        await pg.screenshot(path="/root/build/news-image24/entry.png")
        await b.close()
asyncio.run(main())
