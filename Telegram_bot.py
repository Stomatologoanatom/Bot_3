import feedparser
from datetime import datetime, timedelta, timezone
import httpx
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Загружаем переменные из .env
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

FEEDS = [
    "https://feeds.reuters.com/reuters/worldNews",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.cnn.com/rss/edition_world.rss",
    "https://rss.cnn.com/rss/cnn_allpolitics.rss",
    "https://www.bloomberg.com/feed/podcast/politics.xml",
    "https://www.nbcnews.com/id/3032553/device/rss/rss.xml",
    "https://apnews.com/rss/apf-politics"
]

def is_recent(entry, hours=48):
    if 'published_parsed' in entry:
        pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - pub_date
        print(f"🕒 {entry.title[:30]} — опубликовано {delta} назад")
        return delta <= timedelta(hours=hours)
    return False

async def translate_text(text: str) -> str:
    if not text.strip():
        return "(нет текста для перевода)"
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {"q": text, "langpair": "en|ru"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            translated = data.get("responseData", {}).get("translatedText")
            if not translated:
                print(f"⚠️ Пустой ответ от API: {response.text}")
                return "(ошибка перевода: пустой ответ)"
            return translated
    except Exception as e:
        print(f"❌ Ошибка перевода: {e}")
        return f"(ошибка перевода: {e})"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот, который собирает и переводит свежие новости. Используй /news.")

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Сканирую источники, собираю свежие новости...")

    for url in FEEDS:
        print(f"📡 Обрабатываю источник: {url}")
        feed = feedparser.parse(url)
        count = 0
        for entry in feed.entries:
            if count >= 3:
                break
            if is_recent(entry):
                title = await translate_text(entry.title)
                summary = await translate_text(entry.get("summary", ""))
                link = entry.link

                message = f"📰 <b>{title}</b>\n{summary}\n<a href=\"{link}\">Источник</a>"
                await update.message.reply_text(message, parse_mode="HTML", disable_web_page_preview=True)
                print(f"✅ Отправлена новость: {title}")
                count += 1

    await update.message.reply_text("✅ Новости за сегодня отправлены.")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден. Убедитесь, что .env создан и содержит токен.")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news))
    print("✅ Бот запущен и ожидает сообщений.")
    app.run_polling()