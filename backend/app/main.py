from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from backend.app.api import analytics, auth, cameras, health, pages, products, sessions, tracking, users
from backend.app.config import settings
from backend.app.db import init_db
from backend.app.services.marketing_agent import start_marketing_agent, stop_marketing_agent


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    start_marketing_agent()
    yield
    stop_marketing_agent()


app = FastAPI(title="WatcherMart", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

static_dir = Path(__file__).resolve().parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(cameras.router)
app.include_router(sessions.router)
app.include_router(analytics.router)
app.include_router(tracking.router)
app.include_router(pages.router)
