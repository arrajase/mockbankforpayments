from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.mockbank.api.routes import accounts, customers, transactions, upi, upi_gateway, webhooks
from app.mockbank.db.database import Base, engine
from app.mockbank.db import models  # noqa: F401  (ensures models are registered before create_all)
from app.mockbank.db.seed import seed_gen_ledger, seed_tran_type

Base.metadata.create_all(bind=engine)
seed_gen_ledger()
seed_tran_type()

app = FastAPI(title="Mock Bank API")

WEB_DIR = Path(__file__).parent / "app" / "mockbank" / "web"

app.include_router(customers.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(upi.router)
app.include_router(upi_gateway.router)
app.include_router(webhooks.router)

app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/")
def login_page():
    return FileResponse(WEB_DIR / "pages" / "login.html")


@app.get("/signup")
def signup_page():
    return FileResponse(WEB_DIR / "pages" / "signup.html")


@app.get("/profile")
def profile_page():
    return FileResponse(WEB_DIR / "pages" / "profile.html")


@app.get("/create-account")
def create_account_page():
    return FileResponse(WEB_DIR / "pages" / "create-account.html")


@app.get("/account")
def account_page():
    return FileResponse(WEB_DIR / "pages" / "account.html")


@app.get("/post-transaction")
def post_transaction_page():
    return FileResponse(WEB_DIR / "pages" / "post-transaction.html")


@app.get("/account-statement")
def account_statement_page():
    return FileResponse(WEB_DIR / "pages" / "account-statement.html")


@app.get("/create-upi")
def create_upi_page():
    return FileResponse(WEB_DIR / "pages" / "create-upi.html")


@app.get("/edit-upi")
def edit_upi_page():
    return FileResponse(WEB_DIR / "pages" / "edit-upi.html")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
