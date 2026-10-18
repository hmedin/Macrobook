from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import books, core, restaurant

app = FastAPI(title="Macrobook API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(core.router, prefix="/api")
app.include_router(books.router, prefix="/api")
app.include_router(restaurant.router, prefix="/api")


@app.get("/health")
def health():
    return {"ok": True}
