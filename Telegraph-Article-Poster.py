###Maybe I'm Grey? Never mind###

import requests
from bs4 import BeautifulSoup
import vk_api
import json
from telegraph import Telegraph, exceptions as telegraph_exceptions
from urllib.parse import unquote
import time
import random

# Параметры
vk_api_key = ''
TELEGRAPH_API_KEY = ""
TELEGRAPH_AUTHOR_NAME = ""
TELEGRAPH_AUTHOR_URL = ""

TELEGRAM_API_KEY = ""
TELEGRAM_API_URL = "" + TELEGRAM_API_KEY
TELEGRAM_CHANNEL_ID = ""
TELEGRAM_SEND_METHOD = "/sendMessage"
TELEGRAM_POST_URL = TELEGRAM_API_URL + TELEGRAM_SEND_METHOD
 
GROUP_ID = ""
GROUP_SHORT_NAME = ""

vk_session = vk_api.VkApi(token=vk_api_key)
vk = vk_session.get_api()
telegraph = Telegraph(TELEGRAPH_API_KEY)

def get_link(vk):
    # Получение 20 последних постов
    response = vk.wall.get(owner_id=GROUP_ID, count=20, filter='owner', extended=0)

    # Извлечение ссылок на статьи и описаний постов
    links = []
    descriptions = []
    for item in response['items']:
        # Пропуск рекламных постов
        if item.get('marked_as_ads') == 1:
            continue
        if 'attachments' in item:
            for attachment in item['attachments']:
                if attachment['type'] == 'link':
                    url = attachment['link']['url']
                    if "https://m.vk.com/@{GROUP_SHORT_NAME}" in url:
                        links.append(url)
                        descriptions.append(item['text'])
    return links, descriptions

def get_html_content(link):
    # Получение HTML-кода страницы
    response = requests.get(link)
    
    soup = BeautifulSoup(response.text, 'html.parser')

    ALLOWED_TAGS = [
        'a', 'aside', 'b', 'blockquote', 'br', 'code', 'em', 'figcaption', 'figure',
        'h3', 'h4', 'hr', 'i', 'iframe', 'img', 'li', 'ol', 'p', 'pre', 's',
        'strong', 'u', 'ul', 'video'
    ]

    def filter_allowed_tags(soup, allowed_tags):
        tags = []
        for tag in soup.find_all(allowed_tags):
            if tag not in tags and not any(str(tag) in str(t) for t in tags if t != tag):
                for inner_tag in tag.find_all():
                    if inner_tag.name not in allowed_tags:
                        inner_tag.unwrap()
                tags += [tag]
        return tags
        
    for img in soup.find_all('div', class_="article_object_sizer_wrap"):
        img.find('img')['src'] = json.loads(img.attrs['data-sizes'])[0]['x'][0]

    # Удаление всех div с классом "article__info_line"
    for div in soup.find_all('div', class_="article__info_line"):
        div.decompose()

    # Замена ссылок, содержащих "/away.php?to="
    for a in soup.find_all('a', href=True):
        if "/away.php?to=" in a['href']:
            a['href'] = unquote(a['href'].replace("/away.php?to=", ""))

    article_div = soup.find("div", {"class": "article_view"})
    article_title = soup.find("h1").text

    arr = filter_allowed_tags(article_div, ALLOWED_TAGS)

    result = soup.new_tag("div")

    for el in arr:
        result.append(el)

    return (article_title, result.prettify())

def post_article_telegraph(article, link, description):
    source = article[1]
    source = source.replace("<div>", "").replace("</div>", "")
    try:
        response = telegraph.create_page(
            article[0],
            html_content=source,
            author_name=TELEGRAPH_AUTHOR_NAME,
            author_url=TELEGRAPH_AUTHOR_URL
        )
        print(f"\nОпубликована по ссылке: {response['url']}")
        # Запись ссылки на статью и URL статьи в Telegraph в файл
        with open('post.txt', 'a', encoding='utf-8') as f:
            f.write(link + '\n' + response['url'] + '\n')
        time.sleep(2)  # Пауза в 2 секунды
        # Отправка ссылки на статью в телеграф в группу в телеграм
        post_article_telegram(response['url'], description)
        return response['url']
    except Exception as e:
        print(f"Error: {e}")
        if "CONTENT_TOO_BIG" in str(e):
            print(f"Ошибка при публикации {link}, CONTENT_TOO_BIG")
            # Запись ссылки на статью VK в файл, даже если возникает ошибка CONTENT_TOO_BIG
            with open('post.txt', 'a', encoding='utf-8') as f:
                f.write(link + '\n')
            return "CONTENT_TOO_BIG"
        else:
            raise Exception("Telegram Post Publication Err")

def post_article_telegram(text, description):
    description = description.replace('@{GROUP_SHORT_NAME}', '')
    r = requests.post(url=TELEGRAM_POST_URL, json={
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": description + '\n\n' + text,  # добавление пустой строки между описанием и ссылкой
        "link_preview_options": {
            "prefer_large_media": True,  # Увеличенное медиа в превью ссылок
            "prefer_small_media": False,
            "is_disabled": False
        }
    })
    time.sleep(2)  # Пауза в 2 секунды
    if r.status_code != 200:
        raise Exception("Telegram Post Publication Err")
 
    message_id = r.json()["result"]["message_id"] # Получение ID отправленного сообщения
    reactions = ["❤", "👍", "🔥"] # Список возможных реакций
    reaction = random.choice(reactions) # Выбор случайной реакции из списка

    # Добавление реакции на сообщение
    reaction_url = TELEGRAM_API_URL + "/setMessageReaction"
    response = requests.post(url=reaction_url, json={
        "chat_id": TELEGRAM_CHANNEL_ID,
        "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": reaction}],
    })

    print(f"\nСтатья опубликована с описанием:\n {description}")

if __name__ == "__main__":
    links, descriptions = get_link(vk)
    for link, description in zip(links, descriptions):
        # Проверка, есть ли ссылка уже в файле
        with open('post.txt', 'a+', encoding='utf-8') as f:
            f.seek(0)  # перемещаем указатель в начало файла перед чтением
            if link not in f.read():
                article_title, html_content = get_html_content(link)
                # Если html_content равно None, пропустить эту итерацию цикла
                if html_content is None:
                    continue
                # Создание страницы в Telegraph
                post_article_telegraph((article_title, html_content), link, description)

