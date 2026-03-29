import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import (
    router_admin,
    router_class_storage,
    router_curriculum,
    router_department_storage,
    router_drive,
    router_notifications, # Added router_notifications
    router_signing,
    router_submissions,
)

# Import from our new database file
from .database import create_db_and_tables
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run on startup
    print("Starting up...")
    print("Creating database and tables...")
    create_db_and_tables()  # This creates tables from models.py
    yield
    # Run on shutdown
    print("Shutting down...")


# CORS Configuration - Parse origins from settings
raw_origins = settings.CORS_ALLOWED_ORIGINS
if raw_origins:
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
else:
    # Fallback to defaults if not set
    origins = [
        "http://localhost:3001",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3000",
    ]

# Allow additional origins from environment variable
env_origins = os.getenv("ALLOWED_ORIGINS", "")
if env_origins:
    origins.extend([origin.strip() for origin in env_origins.split(",") if origin.strip()])


app = FastAPI(
    title="HPC Drive Microservice",
    description="Drive service for the college management system",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, PUT, DELETE, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers (Authorization, Content-Type, etc.)
)


# Include the routers
app.include_router(router_drive.router, prefix="/api/v1")
app.include_router(router_admin.router, prefix="/api/v1")
app.include_router(router_notifications.router, prefix="/api/v1")
app.include_router(router_class_storage.router, prefix="/api/v1")
app.include_router(router_department_storage.router, prefix="/api/v1")
app.include_router(router_signing.router, prefix="/api/v1")
app.include_router(router_curriculum.router, prefix="/api/v1")
app.include_router(router_submissions.router, prefix="/api/v1")  # Student submissions


@app.get("/health")
def health_check():
    return {"status": "ok"}


# uvicorn --app-dir src hpc_drive.main:app --host 0.0.0.0 --port 7777 --reload