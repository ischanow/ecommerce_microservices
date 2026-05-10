from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy import create_engine, Column, Integer, String, Float, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
import redis
import json
import os

# Database Setup
os.makedirs("data", exist_ok=True)
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/orders.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis Setup
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

# Models
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_token = Column(String) # In production, extract user ID from JWT
    items = Column(JSON)
    total_amount = Column(Float)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Order Service",
    openapi_url="/openapi.json",
    docs_url="/docs",
    root_path="/api/orders"      # Здесь путь для сервиса заказов
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class CartItem(BaseModel):
    product_id: int
    quantity: int
    price: float

# Endpoints
@app.post("/cart")
def add_to_cart(item: CartItem, authorization: str = Header(...)):
    user_id = authorization.split(" ")[1] # Extract token
    cart_key = f"cart:{user_id}"
    
    current_cart = redis_client.get(cart_key)
    cart = json.loads(current_cart) if current_cart else []
    
    cart.append(item.dict())
    redis_client.set(cart_key, json.dumps(cart))
    return {"message": "Item added to cart", "cart": cart}

@app.get("/cart")
def get_cart(authorization: str = Header(...)):
    user_id = authorization.split(" ")[1]
    cart_key = f"cart:{user_id}"
    current_cart = redis_client.get(cart_key)
    return json.loads(current_cart) if current_cart else []

@app.post("/checkout")
def checkout(authorization: str = Header(...), db: Session = Depends(get_db)):
    user_token = authorization.split(" ")[1]
    cart_key = f"cart:{user_token}"
    
    current_cart = redis_client.get(cart_key)
    if not current_cart:
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    items = json.loads(current_cart)
    total = sum(item["price"] * item["quantity"] for item in items)
    
    new_order = Order(user_token=user_token, items=items, total_amount=total)
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    
    redis_client.delete(cart_key) # Clear cart after order
    return {"message": "Order placed successfully", "order_id": new_order.id, "total": total}