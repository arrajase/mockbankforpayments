"""The only code that changes balances.

Callers must not commit between locking and writing: the balance change, both legs, the
idempotency row and the outbox events are committed together by the caller.
"""

from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import AccountModel, GenLedgerModel, TransactionHistoryModel, TranTypeModel, UpiModel
from app.mockbank.models.schemas import PostingType, TranType
from app.mockbank.services import events
from app.mockbank.utils.common import ist_today, new_id, utcnow

FUND_TRANSFER_TO_TYPE = "Fund Transfer To"
FUND_TRANSFER_FROM_TYPE = "Fund Transfer From"

GL_NAME_BY_TRAN_TYPE = {
    TranType.ATM_DEPOSIT: "Liability",
    TranType.ATM_WITHDRAWAL: "Liability",
    TranType.ATM_FEES: "Income",
    TranType.POS_PURCHASE: "Liability",
    TranType.CASH_BACK: "Liability",
    TranType.CREDIT_INTEREST: "Liability",
}


def posting_type_for(db: Session, posting_name: str) -> str:
    row = db.get(TranTypeModel, posting_name)
    if row is None:
        raise BankError("INTERNAL_ERROR", f"no TRAN_TYPE entry for '{posting_name}'")
    return row.POSTING_TYPE


def _gl_account_for(db: Session, gl_name: str) -> str:
    row = db.query(GenLedgerModel).filter(GenLedgerModel.GL_NAME == gl_name).first()
    if row is None:
        raise BankError("INTERNAL_ERROR", f"no GEN_LDGR entry for '{gl_name}'")
    return row.GL_ACCOUNT


def lock_accounts(db: Session, account_ids: list[str]) -> dict[str, AccountModel]:
    """SELECT ... FOR UPDATE each account, one at a time in account_id order, so two opposite
    transfers always take their locks in the same order and cannot deadlock."""
    locked: dict[str, AccountModel] = {}
    for account_id in sorted(set(account_ids)):
        account = (
            db.query(AccountModel)
            .filter(AccountModel.account_id == account_id)
            .with_for_update()
            .populate_existing()
            .one_or_none()
        )
        if account is None:
            raise BankError("NOT_FOUND", "account not found")
        locked[account_id] = account
    return locked


def _check_currency(currency: str, *accounts: AccountModel) -> None:
    for account in accounts:
        if account.currency != currency:
            raise BankError(
                "CURRENCY_MISMATCH",
                f"request currency {currency} does not match account currency {account.currency}",
            )


def transfer(
    db: Session,
    *,
    sender_upi: UpiModel,
    recipient_upi: UpiModel,
    amount_cents: int,
    currency: str,
    client_id: str | None,
    client_reference: str | None,
    narration: str | None,
) -> TransactionHistoryModel:
    """Move money between two UPI IDs. Returns the sender leg.

    Insufficient funds is a recorded outcome, not an exception: a FAILED sender leg is written
    so the client can look the payment up by its reference.
    """
    if sender_upi.upi_id == recipient_upi.upi_id:
        raise BankError("SAME_UPI", "sender and recipient are the same UPI ID")
    if sender_upi.account_id == recipient_upi.account_id:
        raise BankError("SAME_UPI", "sender and recipient UPI IDs are linked to the same account")
    for upi in (sender_upi, recipient_upi):
        if upi.status != "ACTIVE":
            raise BankError("UPI_INACTIVE", f"UPI ID {upi.upi_id} is not active")

    accounts = lock_accounts(db, [sender_upi.account_id, recipient_upi.account_id])
    sender_account = accounts[sender_upi.account_id]
    recipient_account = accounts[recipient_upi.account_id]
    _check_currency(currency, sender_account, recipient_account)

    now = utcnow()
    common = dict(amount=amount_cents, currency=currency, narration=narration, created_at=now, tran_date=ist_today(now))
    debit_type = posting_type_for(db, FUND_TRANSFER_TO_TYPE)

    if sender_account.balance_cents < amount_cents:
        failed = TransactionHistoryModel(
            transaction_id=new_id("txn"),
            account_id=sender_account.account_id,
            tran_type=FUND_TRANSFER_TO_TYPE,
            posting_type=debit_type,
            status="FAILED",
            failure_reason="INSUFFICIENT_FUNDS",
            client_id=client_id,
            client_reference=client_reference,
            upi_id=sender_upi.upi_id,
            counterparty_upi_id=recipient_upi.upi_id,
            balance_after_cents=sender_account.balance_cents,
            **common,
        )
        db.add(failed)
        return failed

    sender_account.balance_cents -= amount_cents
    recipient_account.balance_cents += amount_cents
    transfer_id = new_id("trf")

    sender_leg = TransactionHistoryModel(
        transaction_id=new_id("txn"),
        account_id=sender_account.account_id,
        tran_type=FUND_TRANSFER_TO_TYPE,
        posting_type=debit_type,
        status="SUCCESS",
        client_id=client_id,
        client_reference=client_reference,
        transfer_id=transfer_id,
        upi_id=sender_upi.upi_id,
        counterparty_upi_id=recipient_upi.upi_id,
        balance_after_cents=sender_account.balance_cents,
        **common,
    )
    recipient_leg = TransactionHistoryModel(
        transaction_id=new_id("txn"),
        account_id=recipient_account.account_id,
        tran_type=FUND_TRANSFER_FROM_TYPE,
        posting_type=posting_type_for(db, FUND_TRANSFER_FROM_TYPE),
        status="SUCCESS",
        client_id=client_id,
        transfer_id=transfer_id,
        upi_id=recipient_upi.upi_id,
        counterparty_upi_id=sender_upi.upi_id,
        balance_after_cents=recipient_account.balance_cents,
        **common,
    )
    db.add_all([sender_leg, recipient_leg])
    events.emit_transaction_posted(db, [sender_leg, recipient_leg], accounts)
    return sender_leg


def post_single(
    db: Session,
    *,
    account_id: str,
    tran_type: TranType,
    amount_cents: int,
    currency: str | None = None,
    upi_id: str | None = None,
    client_id: str | None = None,
    client_reference: str | None = None,
    narration: str | None = None,
    record_failure: bool = False,
) -> TransactionHistoryModel:
    """Post a deposit, withdrawal, fee, etc. against one account plus its general-ledger contra leg.

    With record_failure, insufficient funds writes a FAILED leg (gateway); otherwise it raises (website).
    """
    accounts = lock_accounts(db, [account_id])
    account = accounts[account_id]
    if currency is not None:
        _check_currency(currency, account)

    posting_name = tran_type.value
    contra_name = f"Contra {posting_name}"
    customer_posting_type = posting_type_for(db, posting_name)
    contra_posting_type = posting_type_for(db, contra_name)
    gl_account = _gl_account_for(db, GL_NAME_BY_TRAN_TYPE[tran_type])

    now = utcnow()
    common = dict(amount=amount_cents, currency=account.currency, narration=narration, created_at=now, tran_date=ist_today(now))
    leg_fields = dict(
        account_id=account.account_id,
        tran_type=posting_name,
        posting_type=customer_posting_type,
        client_id=client_id,
        client_reference=client_reference,
        upi_id=upi_id,
        **common,
    )

    is_debit = customer_posting_type == PostingType.DEBIT.value
    if is_debit and account.balance_cents < amount_cents:
        if not record_failure:
            raise BankError("INSUFFICIENT_FUNDS", "insufficient funds")
        failed = TransactionHistoryModel(
            transaction_id=new_id("txn"),
            status="FAILED",
            failure_reason="INSUFFICIENT_FUNDS",
            balance_after_cents=account.balance_cents,
            **leg_fields,
        )
        db.add(failed)
        return failed

    account.balance_cents += -amount_cents if is_debit else amount_cents
    transfer_id = new_id("trf")
    customer_leg = TransactionHistoryModel(
        transaction_id=new_id("txn"),
        status="SUCCESS",
        transfer_id=transfer_id,
        balance_after_cents=account.balance_cents,
        **leg_fields,
    )
    gl_leg = TransactionHistoryModel(
        transaction_id=new_id("txn"),
        account_id=gl_account,
        tran_type=contra_name,
        posting_type=contra_posting_type,
        status="SUCCESS",
        transfer_id=transfer_id,
        **common,
    )
    db.add_all([customer_leg, gl_leg])
    events.emit_transaction_posted(db, [customer_leg], accounts)
    return customer_leg
