import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from openai import AsyncOpenAI

import config
from utils.news_utils import fetch_all_news

# Настройка логирования
os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

bot = Bot(token=config.TELEGRAM_TOKEN)
dp = Dispatcher()

openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

def get_topics_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=topic)] for topic in config.TOPICS.keys()
        ],
        resize_keyboard=True
    )

async def annotate_news(news_item):
    prompt = (
        f"Проаннотируй новость в формате 'Кто? Где? Когда? Что сделал?'. "
        f"Если невозможно, просто сделай краткую аннотацию. "
        f"Объем — 5 предложений, язык — русский.\n\n"
        f"Заголовок: {news_item['title']}\n"
        f"Описание: {news_item['description']}"
    )
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты профессиональный новостной редактор."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"[OPENAI] Ошибка аннотации: {e}")
        return "Не удалось получить аннотацию для этой новости."

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    logging.info(f"[USER] {message.from_user.id} — старт")
    await message.answer(
        "Привет! Выбери интересующую тематику новостей:",
        reply_markup=get_topics_keyboard()
    )

@dp.message(Command("stop"))
async def stop_handler(message: types.Message):
    logging.info(f"[USER] {message.from_user.id} — /stop")
    await message.answer(
        "Работа бота была прервана.\n\nВыберите новую тематику новостей:",
        reply_markup=get_topics_keyboard()
    )

@dp.message(F.text.in_(config.TOPICS.keys()))
async def topic_selected(message: types.Message):
    topic = message.text
    filename = config.TOPICS[topic]
    file_path = os.path.join(config.TOPICS_DIR, filename)
    logging.info(f"[USER] {message.from_user.id} выбрал тему: {topic} ({filename})")
    if not os.path.exists(file_path):
        await message.answer("Файл с источниками не найден. Обратитесь к администратору.")
        logging.error(f"[FILE] Не найден: {file_path}")
        return
    # Чтение источников
    with open(file_path, 'r', encoding='utf-8') as f:
        sources = [line.strip() for line in f if line.strip()]
    if not sources:
        await message.answer("В этом разделе пока нет источников.")
        logging.info(f"[TOPIC] Нет источников в {filename}")
        return

    await message.answer("Загружаю новости. Это может занять некоторое время...")

    news = await fetch_all_news(sources, max_items=config.NEWS_PER_SOURCE)
    if not news:
        await message.answer("Не удалось найти новости по выбранной теме.")
        return

    count = 0
    for news_item in news:
        if not news_item['title'] or not news_item['link']:
            continue
        annotation = await annotate_news(news_item)
        msg = (
            f"<b>{news_item['title']}</b>\n\n"
            f"{annotation}\n"
            f"<a href='{news_item['link']}'>Источник</a>"
        )
        try:
            await message.answer(msg, parse_mode="HTML", disable_web_page_preview=False)
            count += 1
        except Exception as e:
            logging.error(f"[SEND] Ошибка отправки сообщения: {e}")

    await message.answer(f"Готово! Было отправлено {count} новостей.\n\nМожешь выбрать другую тему:", reply_markup=get_topics_keyboard())

# Ловим случайные сообщения
@dp.message()
async def fallback_handler(message: types.Message):
    await message.answer("Пожалуйста, выберите тему новостей из списка.", reply_markup=get_topics_keyboard())

if __name__ == "__main__":
    logging.info("[START] Бот запущен")
    asyncio.run(dp.start_polling(bot))