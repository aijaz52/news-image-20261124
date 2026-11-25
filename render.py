import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    root = Path(__file__).resolve().parent
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width":1024,"height":1024})
        await pg.goto((root / "news.html").as_uri())
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=str(root / "entry.png"))
        await b.close()
asyncio.run(main())
