from sqlalchemy.orm import Session
import model
import schemas


def get_product(db: Session, product_id: int):
    return db.query(model.Product).filter(model.Product.id == product_id).first()

def get_products(db: Session, skip: int = 0, limit: int = 10):
    return db.query(model.Product).offset(skip).limit(limit).all()

def create_product(db: Session, product: schemas.ProductCreate):
    db_product = model.Product(name=product.name, price=product.price)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def update_product(db: Session, product_id: int, product: schemas.ProductCreate):
    db_product = db.query(model.Product).filter(model.Product.id == product_id).first()
    if db_product:
        db_product.name = product.name
        db_product.price = product.price
        db.commit()
        db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: int):
    db_product = db.query(model.Product).filter(model.Product.id == product_id).first()
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product
