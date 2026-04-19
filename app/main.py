import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)

from app import config
from app.router import router
from app.scheduler import start_scheduler, stop_scheduler
from app.services.calendar import init_calendar_service
from app.services.session import init_session_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate_config()
    init_session_store()
    init_calendar_service()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
