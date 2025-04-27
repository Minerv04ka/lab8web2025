from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import List
from datetime import timedelta
import databases
import logging
import time
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.models import Book, BookCreate, User, UserCreate, UserInDB
from app.database import get_db
from app.auth import create_access_token, get_current_user

# Configure logging
logging.basicConfig(
    filename="../api.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Library API", description="API для управління книгами з автентифікацією", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Allow React frontend
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

DATABASE_URL = "sqlite:///./library.db"
database = databases.Database(DATABASE_URL)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database models
class BookDB(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    author = Column(String)
    price = Column(Float)

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

# Create database tables
Base.metadata.create_all(bind=engine)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = "your-secret-key"  # Change this in production!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Middleware for logging requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.3f}s"
    )
    return response

# Startup and shutdown events
@app.on_event("startup")
async def startup():
    await database.connect()
    logger.info("Application started and database connected")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
    logger.info("Application shutdown and database disconnected")

# Authentication endpoints
@app.post("/register", response_model=User)
async def register_user(user: UserCreate):
    logger.info(f"POST /register - Registering user: {user.email}")
    async with get_db() as db:
        query = "SELECT * FROM users WHERE email = :email"
        existing_user = await database.fetch_one(query, {"email": user.email})
        if existing_user:
            logger.warning(f"User with email {user.email} already exists")
            raise HTTPException(status_code=400, detail="Email already registered")
        hashed_password = pwd_context.hash(user.password)
        query = "INSERT INTO users (email, hashed_password) VALUES (:email, :hashed_password) RETURNING id, email"
        values = {"email": user.email, "hashed_password": hashed_password}
        created_user = await database.fetch_one(query, values)
        return created_user

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    logger.info(f"POST /token - Login attempt for user: {form_data.username}")
    async with get_db() as db:
        query = "SELECT * FROM users WHERE email = :email"
        user = await database.fetch_one(query, {"email": form_data.username})
        if not user or not pwd_context.verify(form_data.password, user["hashed_password"]):
            logger.warning(f"Invalid login attempt for user: {form_data.username}")
            raise HTTPException(status_code=400, detail="Incorrect email or password")
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["email"]}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}

# Protected CRUD operations
@app.get("/books", response_model=List[Book])
async def get_books(current_user: UserInDB = Depends(get_current_user)):
    logger.info(f"GET /books - User: {current_user.email}")
    query = "SELECT * FROM books"
    return await database.fetch_all(query)

@app.get("/books/{book_id}", response_model=Book)
async def get_book(book_id: int, current_user: UserInDB = Depends(get_current_user)):
    logger.info(f"GET /books/{book_id} - User: {current_user.email}")
    query = "SELECT * FROM books WHERE id = :id"
    book = await database.fetch_one(query, {"id": book_id})
    if book is None:
        logger.warning(f"Book with id {book_id} not found")
        raise HTTPException(status_code=404, detail="Book not found")
    return book

@app.post("/books", response_model=Book, status_code=status.HTTP_201_CREATED)
async def create_book(book: BookCreate, current_user: UserInDB = Depends(get_current_user)):
    logger.info(f"POST /books - Creating book: {book.title} - User: {current_user.email}")
    query = "INSERT INTO books (title, author, price) VALUES (:title, :author, :price) RETURNING *"
    values = {"title": book.title, "author": book.author, "price": book.price}
    created_book = await database.fetch_one(query, values)
    return created_book

@app.put("/books/{book_id}", response_model=Book)
async def update_book(book_id: int, book: BookCreate, current_user: UserInDB = Depends(get_current_user)):
    logger.info(f"PUT /books/{book_id} - Updating book: {book.title} - User: {current_user.email}")
    query = "UPDATE books SET title = :title, author = :author, price = :price WHERE id = :id RETURNING *"
    values = {"id": book_id, "title": book.title, "author": book.author, "price": book.price}
    updated_book = await database.fetch_one(query, values)
    if updated_book is None:
        logger.warning(f"Book with id {book_id} not found")
        raise HTTPException(status_code=404, detail="Book not found")
    return updated_book

@app.delete("/books/{book_id}")
async def delete_book(book_id: int, current_user: UserInDB = Depends(get_current_user)):
    logger.info(f"DELETE /books/{book_id} - User: {current_user.email}")
    query = "DELETE FROM books WHERE id = :id RETURNING *"
    deleted_book = await database.fetch_one(query, {"id": book_id})
    if deleted_book is None:
        logger.warning(f"Book with id {book_id} not found")
        raise HTTPException(status_code=404, detail="Book not found")
    return {"message": "Book deleted successfully"}