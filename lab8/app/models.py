from pydantic import BaseModel, EmailStr, Field

class BookBase(BaseModel):
    title: str = Field(..., max_length=255)
    author: str = Field(..., max_length=100)
    price: float = Field(..., ge=0)

class BookCreate(BookBase):
    pass

class Book(BookBase):
    id: int

    class Config:
        from_attributes = True

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class User(UserBase):
    id: int

    class Config:
        from_attributes = True

class UserInDB(User):
    hashed_password: str