"""Turn database rows into the JSON shapes clients and the website see."""

from app.mockbank.db.models import CollectRequestModel, ConsentModel, TransactionHistoryModel
from app.mockbank.utils.common import iso_utc


def transaction_record(leg: TransactionHistoryModel, viewer_client_id: str | None = None) -> dict:
    """Gateway view of one leg. client_reference is only shown to the client that set it."""
    if leg.posting_type == "Debit":
        sender, recipient = leg.upi_id, leg.counterparty_upi_id
    else:
        sender, recipient = leg.counterparty_upi_id, leg.upi_id
    return {
        "transaction_id": leg.transaction_id,
        "transfer_id": leg.transfer_id,
        "status": leg.status,
        "failure_reason": leg.failure_reason,
        "tran_type": leg.tran_type,
        "posting_type": leg.posting_type,
        "amount_cents": leg.amount,
        "currency": leg.currency,
        "upi_id": leg.upi_id,
        "counterparty_upi_id": leg.counterparty_upi_id,
        "sender_upi_id": sender,
        "recipient_upi_id": recipient,
        "client_reference": leg.client_reference if viewer_client_id and leg.client_id == viewer_client_id else None,
        "narration": leg.narration,
        "balance_after_cents": leg.balance_after_cents,
        "created_at": iso_utc(leg.created_at),
        "tran_date": leg.tran_date.isoformat(),
    }


def website_transaction(leg: TransactionHistoryModel) -> dict:
    return {
        "transaction_id": leg.transaction_id,
        "account_id": leg.account_id,
        "tran_type": leg.tran_type,
        "posting_type": leg.posting_type,
        "amount_cents": leg.amount,
        "currency": leg.currency,
        "status": leg.status,
        "failure_reason": leg.failure_reason,
        "counterparty_upi_id": leg.counterparty_upi_id,
        "narration": leg.narration,
        "balance_after_cents": leg.balance_after_cents,
        "created_at": iso_utc(leg.created_at),
        "tran_date": leg.tran_date,
    }


def collect_record(collect: CollectRequestModel, payee_name: str | None = None) -> dict:
    return {
        "collect_id": collect.collect_id,
        "status": collect.status,
        "failure_reason": collect.failure_reason,
        "payer_upi_id": collect.payer_upi_id,
        "payee_upi_id": collect.payee_upi_id,
        "payee_name": payee_name,
        "amount_cents": collect.amount_cents,
        "currency": collect.currency,
        "client_reference": collect.client_reference,
        "note": collect.note,
        "transaction_id": collect.transaction_id,
        "created_at": iso_utc(collect.created_at),
        "updated_at": iso_utc(collect.updated_at),
        "expires_at": iso_utc(collect.expires_at),
    }


def consent_record(consent: ConsentModel, client_name: str | None = None) -> dict:
    return {
        "consent_id": consent.consent_id,
        "client_name": client_name,
        "upi_id": consent.upi_id,
        "purposes": consent.purposes.split(","),
        "statement_from": consent.statement_from.isoformat() if consent.statement_from else None,
        "statement_to": consent.statement_to.isoformat() if consent.statement_to else None,
        "status": consent.status,
        "created_at": iso_utc(consent.created_at),
        "updated_at": iso_utc(consent.updated_at),
        "expires_at": iso_utc(consent.expires_at),
    }
