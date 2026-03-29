from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import reports, transactions

app = FastAPI(
    title="Balandda Analytics API",
    description="API for balandda.uz financial analytics",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://analytics.berdiev.uz"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router, prefix="/api/v1/transactions", tags=["transactions"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "balandda-api"}
