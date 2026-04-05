import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import admin_catalog, auth, categories, daily_reports, prepayments, reports, structured_reports, transactions, users, wallets

app = FastAPI(
    title="Balandda Analytics API",
    description="API for balandda.uz financial analytics",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://analytics.berdiev.uz",
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(transactions.router, prefix="/api/v1/transactions", tags=["transactions"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(categories.router, prefix="/api/v1/categories", tags=["categories"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(daily_reports.router, prefix="/api/v1/daily-reports", tags=["daily-reports"])
app.include_router(structured_reports.router, prefix="/api/v1/structured", tags=["structured-reports"])
app.include_router(admin_catalog.router, prefix="/api/v1/admin", tags=["admin-catalog"])
app.include_router(prepayments.router, prefix="/api/v1/prepayments", tags=["prepayments"])
app.include_router(wallets.router, prefix="/api/v1/wallets", tags=["wallets"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "balandda-api"}


# Serve frontend static files (production build)
web_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
if os.path.isdir(web_dist):
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="frontend")
