import feedparser
import os
import logging
import requests
import re
import asyncio
from html import unescape
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# RSS источники (исправлены запятые)
FEEDS = [
    "https://feeds.washingtonpost.com/rss/politics?itid=lk_inline_manual_2",
    "https://feeds.washingtonpost.com/rss/national",
    "https://feeds.washingtonpost.com/rss/business",
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "https://www.wsj.com/xml/rss/3_7014.xml",

    "https://www.ft.com/?format=rss",


    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.theguardian.com/world/rss",

    "https://rss.politico.com/politico.xml",
    "http://feeds.skynews.com/feeds/rss/world.xml"
]

# Удаление HTML-тегов
def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return unescape(cleantext).strip()

# Синхронный перевод
def translate_text_sync(text: str, lang_from="en", lang_to="ru") -> str:
    if not text.strip():
        return text
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text[:500], "langpair": f"{lang_from}|{lang_to}"}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return data['responseData']['translatedText']
    except Exception as e:
        logger.error(f"Ошибка перевода текста: {e}")
        return text

# Асинхронная обёртка
async def translate_text(text: str) -> str:
    return await asyncio.to_thread(translate_text_sync, text)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот, который собирает свежие новости. Используй /news.")

# Команда /news
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Сканирую источники, собираю свежие новости...")

    failed_sources = []

    for url in FEEDS:
        logger.info(f"🔄 Обработка источника: {url}")
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки RSS {url}: {e}")
            failed_sources.append(url)
            continue

        if feed.bozo:
            logger.warning(f"⚠️ Проблема с парсингом: {url} — {feed.bozo_exception}")
            failed_sources.append(url)
            continue

        total_news = len(feed.entries)
        logger.info(f"✅ Найдено {total_news} новостей в источнике: {url}")

        entries = feed.entries[:3]  # Ограничение на 3 новости
        logger.info(f"📌 Обрабатываем первые {len(entries)} новости")

        for i, entry in enumerate(entries, start=1):
            title = getattr(entry, 'title', "(без заголовка)")
            summary_raw = entry.get("summary", "") or entry.get("description", "") or ""
            summary = clean_html(summary_raw)
            if not summary:
                summary = "(нет описания)"
            link = getattr(entry, 'link', "")

            logger.info(f"🔸 Новость {i}: {title}")

            translated_title = await translate_text(title)
            translated_summary = await translate_text(summary)

            message = (
                f"📰 <b>{translated_title}</b>\n"
                f"{translated_summary}\n"
                f"<a href=\"{link}\">Источник</a>"
            )

            try:
                await update.message.reply_text(
                    message, parse_mode="HTML", disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке сообщения: {e}")

    if failed_sources:
        logger.warning("⚠️ Не удалось обработать источники:\n" + "\n".join(failed_sources))
        await update.message.reply_text(
            "⚠️ Некоторые источники не были обработаны. Подробности в логах."
        )

    await update.message.reply_text("✅ Новости за сегодня отправлены.")

# Точка входа
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден. Проверь .env файл.")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news))

    logger.info("🚀 Бот успешно запущен и ожидает команд.")
    app.run_polling()
