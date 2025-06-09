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
from bs4 import BeautifulSoup  # Добавляем BeautifulSoup

# --- Логирование ---
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.bot").setLevel(logging.WARNING)
logging.getLogger("telegram.ext._application").setLevel(logging.WARNING)

# --- Загрузка переменных окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# --- Админы ---
try:
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
except ValueError:
    ADMIN_IDS = []
    logger.warning("⚠️ ADMIN_IDS содержит нечисловые значения или не задан.")

# --- Темы и соответствующие файлы ---
THEMES = {
    "🏳️‍⚧️ Европа": "Topics/Europe.txt",
    "🍜 Азия": "Topics/Asia.txt",
    "💵 Америка": "Topics/America.txt",
    "👳‍♂️✈🏢🏢 Ближний Восток": "Topics/MiddleEast.txt",
    "εつ▄█▀█● НАТО": "Topics/NATO.txt"
}

# --- Главное меню ---
def get_main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🚀 Запустить бота"],
            ["⏹ Прервать поиск новостей"]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

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

# --- Перевод текста ---
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

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["searching"] = False
    await update.message.reply_text(
        "Привет! 👋\nНажми кнопку, чтобы выбрать тему новостей.",
        reply_markup=get_main_menu()
    )

# --- Обработка главного меню ---
async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🚀 Запустить бота":
        context.user_data["searching"] = False
        await update.message.reply_text("Выберите тему новостей:", reply_markup=get_theme_menu())

    elif text == "⏹ Прервать поиск новостей":
        if context.user_data.get("searching", False):
            context.user_data["searching"] = False
            await update.message.reply_text("⏹ Поиск новостей прерван.", reply_markup=get_theme_menu())
        else:
            await update.message.reply_text("❗ Поиск новостей не запущен.", reply_markup=get_main_menu())

    elif text in THEMES:
        await handle_theme_choice(update, context)

    else:
        await update.message.reply_text("❓ Непонятная команда. Используйте кнопки меню.", reply_markup=get_main_menu())

# --- Парсинг HTML новостей с сайта ---
async def parse_news_from_html(url: str, context: ContextTypes.DEFAULT_TYPE):
    """Парсим новости с обычной страницы, пример подстроен под сайт с новостями в <h2 class='news-title'>."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Пример: ищем первые 3 новости — заголовок и краткий текст
        # Поменяй эти селекторы под структуру твоего сайта!
        news_items = soup.find_all('h2', class_='news-title', limit=3)

        news_data = []
        for item in news_items:
            title = item.get_text(strip=True)
            # Попробуем взять описание рядом с заголовком
            summary_tag = item.find_next_sibling('p')
            summary = summary_tag.get_text(strip=True) if summary_tag else ""
            # Ссылка на новость
            link_tag = item.find('a')
            link = link_tag['href'] if link_tag and 'href' in link_tag.attrs else url

            news_data.append({
                "title": title,
                "summary": summary,
                "link": link
            })

        return news_data

    except Exception as e:
        logger.warning(f"Ошибка при парсинге HTML с {url}: {e}")
        return []

# --- Обработка выбора темы и парсинг новостей ---
async def handle_theme_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theme = update.message.text
    feed_file = THEMES.get(theme)

    if not feed_file:
        await update.message.reply_text("❌ Неизвестная тема. Выберите тему из меню.")
        return

    if not os.path.exists(feed_file):
        await update.message.reply_text(f"❌ Файл '{feed_file}' не найден.")
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
            await update.message.reply_text("⏹ Поиск новостей прерван пользователем.", reply_markup=get_theme_menu())
            return

        logger.info(f"🔄 Парсинг HTML: {url}")
        news_items = await parse_news_from_html(url, context)

        if not news_items:
            await update.message.reply_text(f"⚠️ Не удалось получить новости с {url}")
            continue

        for news in news_items:
            if not context.user_data.get("searching", False):
                await update.message.reply_text("⏹ Поиск новостей прерван пользователем.", reply_markup=get_theme_menu())
                return

            translated_title = await translate_text(news["title"])
            translated_summary = await translate_text(news["summary"])

            message = (
                f"📰 <b>{translated_title}</b>\n"
                f"{translated_summary}\n"
                f"<a href=\"{news['link']}\">Источник</a>"
            )

            await update.message.reply_text(
                message, parse_mode="HTML", disable_web_page_preview=True
            )

    context.user_data["searching"] = False
    await update.message.reply_text("✅ Новости отправлены.", reply_markup=get_main_menu())

# --- Установка команд ---
async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Запустить бота и выбрать тему")
    ])

# --- Точка входа ---
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден.")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))
    app.post_init = setup_commands

    logger.info("🚀 Бот запущен.")
    app.run_polling()
