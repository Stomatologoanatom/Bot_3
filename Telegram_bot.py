import feedparser
import os
import logging
import requests
import re
import asyncio
from html import unescape
from dotenv import load_dotenv
from telegram import Update, BotCommand, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters
)

# --- Логирование без лишнего шума ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.bot").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._application").setLevel(logging.WARNING)

# --- Загрузка .env ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --- Админ ID ---
try:
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
except ValueError:
    ADMIN_IDS = []
    logger.warning("⚠️ ADMIN_IDS содержит нечисловые значения или не задан.")

# --- Темы и соответствующие файлы ---
THEMES = {
    "🏳️‍⚧️ Европа": "Europe.txt",
    "🍜 Азия": "Asia.txt",
    "💵 Америка": "America.txt",
    "👳‍♂️✈🏢🏢 Ближний Восток": "MiddleEast.txt",
    "εつ▄█▀█● НАТО": "NATO.txt"
    # Добавь свои темы и файлы тут
}

# --- Очистка HTML-тегов ---
def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    return unescape(re.sub(cleanr, '', raw_html)).strip()

# --- Синхронный перевод через MyMemory ---
def translate_text_sync(text: str, lang_from="en", lang_to="ru") -> str:
    if not text.strip():
        return text
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text[:500], "langpair": f"{lang_from}|{lang_to}"}
        response = requests.get(url, params=params, timeout=10)
        return response.json()['responseData']['translatedText']
    except Exception as e:
        logger.error(f"Ошибка перевода: {e}")
        return text

# --- Асинхронная обёртка ---
async def translate_text(text: str) -> str:
    return await asyncio.to_thread(translate_text_sync, text)

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton(theme)] for theme in THEMES.keys()]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👋 Привет! Выбери тематику новостей:", reply_markup=markup)

# --- Обработка выбора темы пользователем ---
async def handle_theme_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theme = update.message.text
    feed_file = THEMES.get(theme)

    if not feed_file:
        await update.message.reply_text("❌ Неизвестная тема. Выбери тему из меню.")
        return

    if not os.path.exists(feed_file):
        await update.message.reply_text(f"❌ Файл источников для темы '{theme}' не найден.")
        return

    with open(feed_file, encoding='utf-8') as f:
        feeds = [line.strip() for line in f if line.strip()]

    if not feeds:
        await update.message.reply_text(f"⚠️ В файле {feed_file} нет источников.")
        return

    await update.message.reply_text("📡 Сканирую источники...")

    for url in feeds:
        logger.info(f"🔄 Обработка источника: {url}")
        try:
            feed = feedparser.parse(url)
            if feed.bozo:
                raise Exception(feed.bozo_exception)

            for entry in feed.entries[:3]:
                title = getattr(entry, 'title', "(без заголовка)")
                summary = clean_html(entry.get("summary", "") or entry.get("description", ""))
                link = getattr(entry, 'link', "")

                translated_title = await translate_text(title)
                translated_summary = await translate_text(summary)

                message = (
                    f"📰 <b>{translated_title}</b>\n"
                    f"{translated_summary}\n"
                    f"<a href=\"{link}\">Источник</a>"
                )

                await update.message.reply_text(
                    message, parse_mode="HTML", disable_web_page_preview=True
                )

        except Exception as e:
            logger.warning(f"❌ Не удалось обработать {url}: {e}")

    await update.message.reply_text("✅ Новости по теме отправлены.")

# --- Установка команды 'Старт' в меню ---
async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Запустить бота и выбрать тему")
    ])

# --- Точка входа ---
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден. Проверь .env файл.")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_theme_choice))

    app.post_init = setup_commands

    logger.info("🚀 Бот запущен.")
    app.run_polling()
