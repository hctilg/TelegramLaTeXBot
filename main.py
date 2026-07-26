from __future__ import annotations
from app.config import load_settings
from app.bot import LatexGuestBot
import logging, asyncio

async def main():
  logging.basicConfig( # Configure logging
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
  )

  settings = load_settings()
  bot = LatexGuestBot(settings)

  try: await bot.start()
  finally: await bot.shutdown()

if __name__ == "__main__":
  try: asyncio.run(main())
  except KeyboardInterrupt: ...