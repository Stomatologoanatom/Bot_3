import os
import logging
import re
import asyncio
import requests
from html import unescape
from dotenv import load_dotenv
from telegram import Update, BotCommand, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from bs4 import BeautifulSoup

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Загрузка переменных окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --- Админы ---
try:
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
except ValueError:
    ADMIN_IDS = []
    logger.warning("⚠️ ADMIN_IDS содержит нечисловые значения или не задан.")

# --- Темы и файлы ---
THEMES = {
    "🏳️‍⚧️ Европа": "Europe.txt",
    "🍜 Азия": "Asia.txt",
    "💵 Америка": "America.txt",
    "👳‍♂️✈🏢🏢 Ближний Восток": "MiddleEast.txt",
    "εつ▄█▀█● НАТО": "NATO.txt"
}

# --- Меню с темами ---
def get_theme_menu():
    return ReplyKeyboardMarkup(
        [[theme] for theme in THEMES.keys()],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# --- Очистка HTML ---
def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    return unescape(re.sub(cleanr, '', raw_html)).strip()

# --- Перевод ---
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

async def translate_text(text: str) -> str:
    return await asyncio.to_thread(translate_text_sync, text)

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["searching"] = False
    await update.message.reply_text(
        "Привет! 👋\nВыберите тему новостей:",
        reply_markup=get_theme_menu()
    )

# --- /stop ---
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("searching", False):
        context.user_data["searching"] = False
        await update.message.reply_text("⏹ Поиск новостей прерван.")
    else:
        await update.message.reply_text("🔇 Поиск новостей не запущен.")

# --- Парсинг HTML ---
async def parse_news_from_html(url: str, context: ContextTypes.DEFAULT_TYPE):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10, verify=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        news_items = soup.find_all('article', limit=3) or soup.find_all('h2', limit=3)

        if not news_items:
            logger.info(f"🔍 На {url} не найдено подходящих тегов")
            return []

        results = []
        for item in news_items:
            title_tag = item.find('a') or item.find('h2')
            title = title_tag.get_text(strip=True) if title_tag else "Без заголовка"
            link = title_tag['href'] if title_tag and title_tag.has_attr('href') else url
            summary_tag = item.find('p')
            summary = summary_tag.get_text(strip=True) if summary_tag else ""
            results.append({
                "title": title,
                "summary": summary,
                "link": link
            })

        return results

    except Exception as e:
        logger.warning(f"Ошибка при парсинге HTML с {url}: {e}")
        return []

# --- Обработка темы ---
async def handle_theme_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theme = update.message.text
    feed_file = THEMES.get(theme)

    if not feed_file or not os.path.exists(feed_file):
        await update.message.reply_text("❌ Неизвестная тема или файл не найден.")
        return

    with open(feed_file, encoding='utf-8') as f:
        feeds = [line.strip() for line in f if line.strip()]

    if not feeds:
        await update.message.reply_text(f"⚠️ В файле {feed_file} нет источников.")
        return

    context.user_data["searching"] = True
    await update.message.reply_text("📡 Получаю новости...")

    for url in feeds:
        if not context.user_data.get("searching", False):
            await update.message.reply_text("⏹ Поиск остановлен.", reply_markup=get_theme_menu())
            return

        logger.info(f"🔄 Парсинг: {url}")
        news_items = await parse_news_from_html(url, context)

        if not news_items:
            await update.message.reply_text(f"⚠️ Не удалось получить новости с {url}")
            continue

        for news in news_items:
            if not context.user_data.get("searching", False):
                await update.message.reply_text("⏹ Поиск остановлен.", reply_markup=get_theme_menu())
                return

            title_ru = await translate_text(news["title"])
            summary_ru = await translate_text(news["summary"])

            message = (
                f"📰 <b>{title_ru}</b>\n"
                f"{summary_ru}\n"
                f"<a href=\"{news['link']}\">Источник</a>"
            )
            await update.message.reply_text(message, parse_mode="HTML", disable_web_page_preview=True)

    context.user_data["searching"] = False
    await update.message.reply_text("✅ Все новости отправлены.", reply_markup=get_theme_menu())

# --- Текстовые кнопки — выбор темы ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in THEMES:
        await handle_theme_choice(update, context)
    else:
        await update.message.reply_text("❓ Пожалуйста, выбери тему из меню.", reply_markup=get_theme_menu())

# --- Команды ---
async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Запустить бота и выбрать тему новостей"),
        BotCommand("stop", "Прервать поиск новостей")
    ])

# --- Запуск ---
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Переменная TELEGRAM_BOT_TOKEN не найдена.")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.post_init = setup_commands

    logger.info("🚀 Бот запущен.")
    app.run_polling()
