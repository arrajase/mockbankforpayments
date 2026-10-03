from sqlalchemy.orm import Session

from app.mockbank.db.models import ApiClientModel, CustomerModel, TransactionHistoryModel
from app.mockbank.core.errors import BankError
from app.mockbank.models.schemas import TransactionCreate
from app.mockbank.services import ledger
from app.mockbank.services.accounts import get_own_account
from app.mockbank.services.records import transaction_record, website_transaction


# ---------- website ----------

def post_own_transaction(db: Session, customer: CustomerModel, payload: TransactionCreate) -> dict:
    """Website test-money form: only against the logged-in customer's own accounts; the bank sets the date."""
    get_own_account(db, customer, payload.account_id)
    leg = ledger.post_single(db, account_id=payload.account_id, tran_type=payload.tran_type, amount_cents=payload.amount_cents)
    db.commit()
    return website_transaction(leg)


def list_own_transactions(db: Session, customer: CustomerModel, account_id: str) -> list[dict]:
    get_own_account(db, customer, account_id)
    rows = (
        db.query(TransactionHistoryModel)
        .filter(TransactionHistoryModel.account_id == account_id, TransactionHistoryModel.status == "SUCCESS")
        .order_by(TransactionHistoryModel.created_at.desc(), TransactionHistoryModel.transaction_id.desc())
        .all()
    )
    return [website_transaction(row) for row in rows]


# ---------- gateway: status lookup ----------

def get_client_transaction(db: Session, client: ApiClientModel, transaction_id: str) -> dict:
    leg = db.get(TransactionHistoryModel, transaction_id)
    if leg is None or leg.client_id != client.client_id:
        raise BankError("TRANSACTION_NOT_FOUND", "transaction not found")
    return transaction_record(leg, viewer_client_id=client.client_id)


def find_by_client_reference(db: Session, client: ApiClientModel, client_reference: str) -> dict:
    leg = (
        db.query(TransactionHistoryModel)
        .filter(
            TransactionHistoryModel.client_id == client.client_id,
            TransactionHistoryModel.client_reference == client_reference,
        )
        .one_or_none()
    )
    if leg is None:
        raise BankError("TRANSACTION_NOT_FOUND", "no transaction with this client_reference")
    return transaction_record(leg, viewer_client_id=client.client_id)


def reference_in_use(db: Session, client_id: str, client_reference: str) -> bool:
    return (
        db.query(TransactionHistoryModel.transaction_id)
        .filter(
            TransactionHistoryModel.client_id == client_id,
            TransactionHistoryModel.client_reference == client_reference,
        )
        .first()
        is not None
    )
