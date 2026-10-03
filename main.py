import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.mockbank.api.routes import accounts, collect, consents, events, transactions, upi, upi_gateway, webhooks, website_auth
from app.mockbank.core.config import WORKER_ENABLED
from app.mockbank.core.errors import register_error_handlers
from app.mockbank.db.seed import seed_gen_ledger, seed_tran_type
from app.mockbank.services import worker

# The schema is managed by Alembic: run `alembic upgrade head` before starting the app.


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_gen_ledger()
    seed_tran_type()
    task = asyncio.create_task(worker.run_forever()) if WORKER_ENABLED else None
    yield
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Mock Bank API", lifespan=lifespan)
register_error_handlers(app)

WEB_DIR = Path(__file__).parent / "app" / "mockbank" / "web"

app.include_router(website_auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(upi.router)
app.include_router(upi_gateway.router)
app.include_router(collect.gateway_router)
app.include_router(collect.website_router)
app.include_router(consents.gateway_router)
app.include_router(consents.website_router)
app.include_router(consents.app_access_router)
app.include_router(events.router)
app.include_router(webhooks.router)

app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

PAGES = {
    "/": "login.html",
    "/signup": "signup.html",
    "/profile": "profile.html",
    "/create-account": "create-account.html",
    "/account": "account.html",
    "/post-transaction": "post-transaction.html",
    "/account-statement": "account-statement.html",
    "/create-upi": "create-upi.html",
    "/edit-upi": "edit-upi.html",
    "/pending-requests": "pending-requests.html",
    "/app-permissions": "app-permissions.html",
}


def _page_route(filename: str):
    def page():
        return FileResponse(WEB_DIR / "pages" / filename)

    return page


for _path, _filename in PAGES.items():
    app.add_api_route(_path, _page_route(_filename), methods=["GET"], include_in_schema=False)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
