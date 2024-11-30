import logging
import time

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bs4 import BeautifulSoup
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

import crud
import schemas
import database
import model

# Настройка логирования
logging.basicConfig(
    filename='parse.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

app = FastAPI()

# Инициализация базы данных
model.Base.metadata.create_all(bind=database.engine)

# Получение сессии базы данных
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Роуты API
@app.post("/products/", response_model=schemas.Product)
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    return crud.create_product(db=db, product=product)

@app.get("/products/", response_model=list[schemas.Product])
def get_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_products(db=db, skip=skip, limit=limit)

@app.get("/products/{product_id}", response_model=schemas.Product)
def get_product(product_id: int, db: Session = Depends(get_db)):
    db_product = crud.get_product(db=db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

@app.put("/products/{product_id}", response_model=schemas.Product)
def update_product(product_id: int, product: schemas.ProductCreate, db: Session = Depends(get_db)):
    db_product = crud.update_product(db=db, product_id=product_id, product=product)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

@app.delete("/products/{product_id}", response_model=schemas.Product)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    db_product = crud.delete_product(db=db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Функция парсинга и записи в базу данных
def parse_and_save_products():
    logging.info("Parsing job started...")
    url = "https://www.maxidom.ru/catalog/dreli/"
    while url:
        try:
            logging.info(f"Запрос к URL: {url}")
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Извлечение данных о товарах
            items = soup.find_all('article', class_='l-product l-product__horizontal')
            for item in items:
                name = item.find('span', itemprop='name').text.strip()
                price = item.find('span', itemprop='price').text.strip()
                price = float(price.replace('₽', '').replace(' ', ''))  # Преобразование цены в число

                # Сохраняем в базу данных, если такой продукт еще не существует
                db = database.SessionLocal()
                existing_product = db.query(model.Product).filter(model.Product.name == name).first()
                if not existing_product:
                    crud.create_product(db=db, product=schemas.ProductCreate(name=name, price=price))
                    logging.info(f"Added product: {name}, Price: {price}")
                else:
                    logging.info(f"Product {name} is already in the database.")
                db.close()

            # Переход на следующую страницу
            next_page = soup.find('a', id='navigation_2_next_page')
            if next_page:
                url = "https://www.maxidom.ru" + next_page.get('href')
                time.sleep(1)
            else:
                url = None

        except Exception as e:
            logging.error(f"Parsing error {url}: {str(e)}")
            break

# Инициализация планировщика задач
scheduler = BackgroundScheduler()

# Добавляем задачу для выполнения каждые 5 минут
scheduler.add_job(
    func=parse_and_save_products,
    trigger=IntervalTrigger(seconds=300),
    id="product_parsing_job",
    name="Parsing data every 5 minutes",
    replace_existing=True,
)

# Запускаем планировщик
scheduler.start()

# Остановка планировщика при завершении работы приложения
@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
    logging.info("Parsing job stopped")
