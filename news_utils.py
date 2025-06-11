import aiohttp
import xml.etree.ElementTree as ET
import logging

async def fetch_rss(session, url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        async with session.get(url, timeout=10, headers=headers) as response:
            content_type = response.headers.get('Content-Type', '')
            if "xml" in content_type or "rss" in content_type:
                return await response.text()
            text = await response.text()
            if text.strip().startswith('<?xml') or '<rss' in text:
                return text
            else:
                logging.warning(f"[RSS] Не удалось определить RSS по ссылке: {url}")
                return None
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
                # Если совсем ничего нет — пропускаем
                if not title or not link:
                    continue
                items.append({
                    'title': title,
                    'link': link,
                    'description': desc,
                    'pubDate': pubdate
                })
        # Google News иногда структура без channel
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