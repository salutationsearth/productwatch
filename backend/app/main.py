from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api import cameras, health, products, sessions, users
from backend.app.config import settings
from backend.app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(cameras.router)
app.include_router(sessions.router)
