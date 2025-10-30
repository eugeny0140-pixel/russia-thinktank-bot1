# russia_thinktank_bot.py
import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import schedule
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@time_n_John")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан в переменных окружения")

# ================== ИСТОЧНИКИ ==================
SOURCES = [
    {"name": "Foreign Affairs", "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "Reuters Institute", "url": "https://reutersinstitute.politics.ox.ac.uk/rss.xml"},
    {"name": "Bruegel", "url": "https://www.bruegel.org/rss.xml"},
    {"name": "E3G", "url": "https://www.e3g.org/feed/"},
    {"name": "Chatham House", "url": "https://www.chathamhouse.org/rss.xml"},
    {"name": "CSIS", "url": "https://www.csis.org/rss.xml"},
    {"name": "Atlantic Council", "url": "https://www.atlanticcouncil.org/feed/"},
    {"name": "RAND Corporation", "url": "https://www.rand.org/rss.xml"},
    {"name": "CFR", "url": "https://www.cfr.org/rss/"},
    {"name": "Carnegie Endowment", "url": "https://carnegieendowment.org/rss.xml"},
    {"name": "The Economist", "url": "https://www.economist.com/latest/rss.xml"},
    {"name": "Bloomberg Politics", "url": "https://www.bloomberg.com/politics/feeds/site.xml"},
]

KEYWORDS = [
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b",
    r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b",
    r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b",
    r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b",
    r"\bmedvedev\b", r"\bpeskov\b", r"\bnato\b", r"\beuropa\b", r"\busa\b",
    r"\bwar\b", r"\bconflict\b", r"\bmilitary\b", r"\bruble\b", r"\beconomy\b",
    r"\benergy\b", r"\boil\b", r"\bgas\b", r"\bsoviet\b", r"\bpost\W?soviet\b"
]

MAX_SEEN = 5000
MAX_PER_RUN = 12
seen_links = set()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def clean_text(t):
    return re.sub(r"\s+", " ", t).strip()

def translate_to_russian(text):
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e:
        log.warning(f"⚠️ Перевод не удался: {e}")
        return text

def get_summary(title):
    low = title.lower()
    if re.search(r"sanction|embargo|restrict", low):
        return "Введены новые санкции или ограничения."
    if re.search(r"war|attack|strike|bomb|conflict|military", low):
        return "Сообщается о военных действиях или ударах."
    if re.search(r"putin|kremlin|peskov|moscow", low):
        return "Заявление или действие со стороны Кремля."
    if re.search(r"economy|rubl?e|oil|gas|gazprom|nord\s?stream|energy", low):
        return "Новости экономики, нефти, газа или рубля."
    if re.search(r"diplomat|talks|negotiat|meeting|lavrov", low):
        return "Дипломатические переговоры или контакты."
    if re.search(r"wagner|shoigu|medvedev|defense", low):
        return "События с российскими военными или политиками."
    if re.search(r"ukraine|zelensky|kyiv|kiev|crimea|donbas", low):
        return "События, связанные с Украиной и прилегающими регионами."
    if re.search(r"nato|europa|european|germany|france|usa|uk", low):
        return "Реакция западных стран или НАТО на события с участием России."
    return "Аналитика, связанная с Россией или постсоветским пространством."

def get_source_prefix(name):
    name = name.lower()
    if "e3g" in name:
        return "e3g"
    elif "foreign affairs" in name:
        return "foreignaffairs"
    elif "chatham house" in name:
        return "chathamhouse"
    elif "csis" in name:
        return "csis"
    elif "atlantic council" in name:
        return "atlanticcouncil"
    elif "rand" in name:
        return "rand"
    elif "cfr" in name:
        return "cfr"
    elif "carnegie" in name:
        return "carnegie"
    elif "bruegel" in name:
        return "bruegel"
    elif "bloomberg" in name:
        return "bloomberg"
    elif "reuters institute" in name:
        return "reuters"
    elif "the economist" in name:
        return "economist"
    else:
        return name.split()[0].lower()

def fetch_rss_news():
    global seen_links
    result = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for src in SOURCES:
        if len(result) >= MAX_PER_RUN:
            break
        try:
            url = src["url"].strip()
            log.info(f"📡 {src['name']}")
            resp = requests.get(url, timeout=30, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "xml")

            for item in soup.find_all("item"):
                if len(result) >= MAX_PER_RUN:
                    break

                title = clean_text(item.title.get_text()) if item.title else ""
                link = (item.link.get_text() or item.guid.get_text()).strip() if item.link or item.guid else ""

                if not title or not link or link in seen_links:
                    continue

                if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                    continue

                # Получаем описание из RSS
                description = ""
                desc_tag = item.find("description") or item.find("content:encoded")
                if desc_tag:
                    desc_html = desc_tag.get_text()
                    desc_soup = BeautifulSoup(desc_html, "html.parser")
                    raw_desc = clean_text(desc_soup.get_text())
                    # Обрезаем до 300–400 символов, но не в середине слова
                    if len(raw_desc) > 400:
                        description = raw_desc[:400].rsplit(' ', 1)[0] + "…"
                    else:
                        description = raw_desc

                # Если описания нет — используем резюме
                if not description.strip():
                    description = get_summary(title)

                ru_title = translate_to_russian(title)
                prefix = get_source_prefix(src["name"])
                msg = f"{prefix}: {ru_title}\n\n{description}\n\nИсточник ({link})"
                result.append({"msg": msg, "link": link})

        except Exception as e:
            log.error(f"❌ {src['name']}: {e}")

    return result

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",  # можно оставить, но текст чистый
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            log.info("✅ Отправлено")
        else:
            log.error(f"❌ Telegram error: {r.text}")
    except Exception as e:
        log.error(f"❌ Исключение: {e}")

def job():
    global seen_links
    log.info("🔄 Проверка новостей по России и геополитике...")
    news = fetch_rss_news()
    if not news:
        log.info("📭 Нет релевантных публикаций.")
        return

    for item in news:
        send_to_telegram(item["msg"])
        seen_links.add(item["link"])
        if len(seen_links) > MAX_SEEN:
            seen_links = set(list(seen_links)[-4000:])
        time.sleep(1)

if __name__ == "__main__":
    log.info("🚀 Бот запущен на Render. Источников: %d", len(SOURCES))
    job()
    schedule.every(30).minutes.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)