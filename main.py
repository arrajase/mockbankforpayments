from fastapi import FastAPI

from app.mockbank.api.routes import accounts, payments, webhooks

app = FastAPI(title="Mock Bank API")

app.include_router(accounts.router)
app.include_router(payments.router)
app.include_router(webhooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
