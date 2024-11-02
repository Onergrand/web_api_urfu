import requests
from bs4 import BeautifulSoup
import time


def parse_category(url):
    while url:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Извлечение данных о товарах
        items = soup.find_all('article', class_='l-product l-product__horizontal')
        for item in items:
            name = item.find('span', itemprop='name').text.strip()
            price = item.find('span', itemprop='price').text.strip()
            # Добавьте другие данные, которые вам нужны

            print(f'Название: {name}, Цена: {price}')

        # Переход на следующую страницу
        next_page = soup.find('a', id='navigation_2_next_page')
        if next_page:
            url = "https://www.maxidom.ru" + next_page.get('href')
            # Пауза чтобы уменьшить нагрузку на сервер и дать странице загрузиться
            time.sleep(1)
        else:
            url = None


category_url = "https://www.maxidom.ru/catalog/dreli/"
parse_category(category_url)
