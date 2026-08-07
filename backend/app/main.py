from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from .api import router
from .config import get_settings
from .db import init_db
from .seed import seed_all, seed_taxonomy

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if get_settings().auto_seed:
        try:
            seed_all() if get_settings().demo_mode else seed_taxonomy()
        except Exception as exc:
            print(f"seed warning: {exc}")
    yield

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

frontend_candidates = [
    Path(__file__).resolve().parents[2] / "frontend",  # repository layout
    Path.cwd() / "frontend",                         # container layout
]
frontend_dir = next((p for p in frontend_candidates if (p / "index.html").exists()), None)
if frontend_dir:
    app.mount("/ui", StaticFiles(directory=frontend_dir, html=True), name="ui")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/" if frontend_dir else "/docs")
