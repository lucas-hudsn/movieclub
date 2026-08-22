from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routers import auth, cycles, movies, rankings

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Movie Club", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

for router in (auth.router, movies.router, rankings.router, cycles.router):
    app.include_router(router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 303 and "Location" in exc.headers:
        return RedirectResponse(exc.headers["Location"], status_code=303)

    from app.templating import templates

    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={"detail": exc.detail},
        status_code=exc.status_code,
    )
