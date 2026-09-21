from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from database import engine
from dotenv import load_dotenv
import models
import os
from routers import businesses, messages, website_checker, scraper, pipeline, webhooks, whatsaap_connection 

load_dotenv()

API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,https://scrape-frontend-iota.vercel.app"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="LeadGen API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    webhooks.router,
    prefix="/api/webhooks",
    tags=["webhooks"],
)

@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Skip preflight and health check
    if (
        request.method == "OPTIONS"
        or request.url.path == "/api/health"
        or request.url.path == "/api/webhooks/evolution"
    ):
        return await call_next(request)

    if API_SECRET_KEY:
        key = request.headers.get("X-API-Key", "")
        if key != API_SECRET_KEY:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    return await call_next(request)


from routers import businesses, messages, website_checker, scraper, pipeline

app.include_router(businesses.router, prefix="/api/businesses", tags=["businesses"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(website_checker.router, prefix="/api/check", tags=["website-checker"])
app.include_router(scraper.router, prefix="/api/scrape", tags=["scraper"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
app.include_router(
    whatsaap_connection.router,
    prefix="/api",
    tags=["evolution-test"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}
