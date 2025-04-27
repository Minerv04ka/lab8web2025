import databases
from contextlib import asynccontextmanager

DATABASE_URL = "sqlite:///./library.db"
database = databases.Database(DATABASE_URL)

@asynccontextmanager
async def get_db():
    await database.connect()
    try:
        yield database
    finally:
        await database.disconnect()