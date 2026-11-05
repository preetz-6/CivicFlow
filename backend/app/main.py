import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.errors import DomainError
from app.modules.auth.router import router as auth_router
from app.modules.system import clock_state
from app.modules.system.router import router as system_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    clock_state.restore_or_init()
    from app.agents.runtime import registry

    registry.register_all()
    if settings.scheduler_enabled:
        from app import scheduler

        scheduler.start()
    yield
    if settings.scheduler_enabled:
        from app import scheduler

        scheduler.stop()


app = FastAPI(
    title="CivicFlow API",
    version="0.1.0",
    description="Agentic civic operations (hackathon prototype). Ingestion contract: see docs/API.md.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(DomainError)
def domain_error(_: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, **exc.detail})


API = "/api/v1"
app.include_router(auth_router, prefix=API)
app.include_router(system_router, prefix=API)
