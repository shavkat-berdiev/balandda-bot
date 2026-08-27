import os

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from db.database import async_session
from api.routers import admin_catalog, auth, bot_templates, bridge, card_transactions, categories, customers, daily_reports, prepayments, public, registration, reports, reservations, spa_schedule, stats, structured_reports, transactions, users, wallets

app = FastAPI(
    title="Balandda Analytics API",
    description="API for balandda.uz financial analytics",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://analytics.berdiev.uz",
        "https://www.balandda.uz",   # website reads the public catalog
        "https://balandda.uz",
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
app.include_router(registration.router, prefix="/api/v1/registration", tags=["registration"])
app.include_router(public.router, prefix="/api/v1/public", tags=["public"])
app.include_router(reservations.router, prefix="/api/v1/reservations", tags=["reservations"])
app.include_router(bridge.router, prefix="/api/v1/bridge", tags=["bridge"])
app.include_router(spa_schedule.router, prefix="/api/v1/spa", tags=["spa-schedule"])
# Unified bot content: /bot-templates (admin) + /bot-flow, /bot-image (public — Meta fetches these)
app.include_router(bot_templates.router, prefix="/api/v1", tags=["bot-templates"])
app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(card_transactions.router, prefix="/api/v1/card-transactions", tags=["card-transactions"])
app.include_router(customers.router, prefix="/api/v1/customers", tags=["customers"])


@app.get("/api/health")
async def health(response: Response):
    """Liveness AND readiness.

    This used to return {"status": "ok"} unconditionally. On 2026-08-27 the Postgres
    container stayed down for three hours after a host reboot while this endpoint
    answered 200 the whole time — the booking calendar and the website's booking flow
    were dead and every monitor was green. A health check that cannot fail is not a
    health check, so it now actually talks to the database.
    """
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any DB failure means "do not send traffic here"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "error",
            "service": "balandda-api",
            "database": "unreachable",
            "detail": type(exc).__name__,
        }
    return {"status": "ok", "service": "balandda-api", "database": "ok"}


# Serve frontend static files (production build)
web_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
if os.path.isdir(web_dist):
    app.mount("/", StaticFiles(directory=web_dist, html=True), name="frontend")
