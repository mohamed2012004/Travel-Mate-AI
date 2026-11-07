from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from router.router import router
from utils.backend_helpers import shutdown_database, startup_database

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database_report = await startup_database()
    yield
    await shutdown_database()


app = FastAPI(
    title="TripMate AI",
    description="LangGraph Multi-Agent Travel Planner with FastAPI Frontend",
    version="1.0.0",
    lifespan=lifespan
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

app.include_router(router)


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
