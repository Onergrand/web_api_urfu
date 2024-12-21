import logging
import aiohttp

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from bs4 import BeautifulSoup
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from fastapi.websockets import WebSocket
from fastapi.websockets import WebSocketDisconnect

import asyncio
import json
import crud
import schemas
import database
import model

connected_clients = []

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

async def send_notification(message: str):
    for client in connected_clients:
        try:
            await client.send_text(json.dumps({"message": message}))
        except:
            connected_clients.remove(client)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # Поддерживаем соединение
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

# Роуты API
@app.post("/products/", response_model=schemas.Product)
async def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    new_product = crud.create_product(db=db, product=product)
    await send_notification(f"Product created: {new_product.name} (ID: {new_product.id})")
    return new_product


@app.get("/products/", response_model=list[schemas.Product])
async def get_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    products = await perform_db_operation_sync(crud.get_products, db, skip, limit)
    await send_notification(f"Products retrieved: {len(products)} items.")
    return products


@app.get("/products/{product_id}", response_model=schemas.Product)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    db_product = await perform_db_operation_sync(crud.get_product, db, product_id)
    if db_product is None:
        await send_notification(f"Product with ID {product_id} not found.")
        raise HTTPException(status_code=404, detail="Product not found")
    await send_notification(f"Product retrieved: {db_product.name} (ID: {db_product.id}).")
    return db_product


@app.put("/products/{product_id}", response_model=schemas.Product)
async def update_product(product_id: int, product: schemas.ProductCreate, db: Session = Depends(get_db)):
    db_product = await perform_db_operation_sync(crud.update_product, db, product_id, product)
    if db_product is None:
        await send_notification(f"Failed to update: Product with ID {product_id} not found.")
        raise HTTPException(status_code=404, detail="Product not found")
    await send_notification(f"Product updated: {db_product.name} (ID: {db_product.id}).")
    return db_product


@app.delete("/products/{product_id}", response_model=schemas.Product)
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    deleted_product = crud.delete_product(db=db, product_id=product_id)
    if deleted_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    await send_notification(f"Product deleted: {deleted_product.name} (ID: {deleted_product.id})")
    return deleted_product

async def perform_db_operation_sync(func, *args, **kwargs):
    loop = asyncio.get_running_loop()  # Получение текущего event loop
    return await loop.run_in_executor(None, func, *args, **kwargs)


# Функция парсинга и записи в базу данных
async def parse_and_save_products():
    logging.info("Parsing job started...")
    url = "https://www.maxidom.ru/catalog/dreli/"
    updated_products = 0
    while url:
        try:
            logging.info(f"Запрос к URL: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')

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
                    updated_products += 1
                    logging.info(f"Added product: {name}, Price: {price}")
                else:
                    logging.info(f"Product {name} is already in the database.")
                db.close()

            # Переход на следующую страницу
            next_page = soup.find('a', id='navigation_2_next_page')
            if next_page:
                url = "https://www.maxidom.ru" + next_page.get('href')
                await asyncio.sleep(1)  # Асинхронный таймаут
            else:
                url = None

        except Exception as e:
            logging.error(f"Parsing error {url}: {str(e)}")
            break

    # Отправка уведомления после обновления базы данных
    await send_notification(f"Database updated. {updated_products} products added or modified.")


# Инициализация планировщика задач
scheduler = AsyncIOScheduler()

# Добавляем задачу для выполнения каждую минуту
scheduler.add_job(
    func=lambda: asyncio.run(parse_and_save_products()),
    trigger=IntervalTrigger(seconds=60),
    id="product_parsing_job",
    name="Parsing data every 1 minute",
    replace_existing=True,
)

# Запускаем планировщик
scheduler.start()

# Остановка планировщика при завершении работы приложения
@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
    logging.info("Parsing job stopped")
