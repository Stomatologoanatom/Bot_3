import aiohttp
import xml.etree.ElementTree as ET
import logging
import config

async def fetch_rss(session, url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        async with session.get(url, timeout=15, headers=headers) as response:
            text = await response.text()
            return text
    except Exception as e:
        logging.error(f"[RSS] Ошибка запроса к {url}: {e}")
        return None

def parse_rss(text, max_items=3):
    items = []
    try:
        root = ET.fromstring(text)
        for channel in root.findall('channel'):
            for item in channel.findall('item')[:max_items]:
                title = item.findtext('title', '').strip()
                link = item.findtext('link', '').strip()
                desc = item.findtext('description', '').strip()
                pubdate = item.findtext('pubDate', '').strip()
                if not title or not link:
                    continue
                items.append({
                    'title': title,
                    'link': link,
                    'description': desc,
                    'pubDate': pubdate
                })
        if not items:
            for item in root.findall('.//item')[:max_items]:
                title = item.findtext('title', '').strip()
                link = item.findtext('link', '').strip()
                desc = item.findtext('description', '').strip()
                pubdate = item.findtext('pubDate', '').strip()
                if not title or not link:
                    continue
                items.append({
                    'title': title,
                    'link': link,
                    'description': desc,
                    'pubDate': pubdate
                })
    except Exception as e:
        logging.error(f"[RSS] Ошибка парсинга RSS: {e}")
    return items

async def fetch_all_news(sources, max_items=3):
    results = []
    async with aiohttp.ClientSession() as session:
        for url in sources:
            text = await fetch_rss(session, url)
            if not text:
                logging.warning(f"[NEWS] Пропущен источник (не RSS или не загрузился): {url}")
                continue
            items = parse_rss(text, max_items)
            if not items:
                logging.info(f"[NEWS] Нет новостей или пустая лента: {url}")
            results.extend(items)
    return results

async def annotate_deepseek(news_item, api_key):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    prompt = (
        f"Проаннотируй новость в формате 'Кто? Где? Когда? Что сделал?'. "
        f"Если невозможно — просто сделай краткую аннотацию. "
        f"Объем — 5 предложений, язык — русский.\n\n"
        f"Заголовок: {news_item['title']}\n"
        f"Описание: {news_item['description']}"
    )
    data = {
        "model": "deepseek-chat",  # если у тебя другой, поправь!
        "messages": [
            {"role": "system", "content": "Ты профессиональный новостной редактор."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 512,
        "temperature": 0.7
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data, timeout=20) as resp:
            if resp.status == 200:
                res = await resp.json()
                return res["choices"][0]["message"]["content"].strip()
            else:
                logging.error(f"[DEEPSEEK] Ошибка ответа: {resp.status}, {await resp.text()}")
                return "Не удалось получить аннотацию для этой новости."
