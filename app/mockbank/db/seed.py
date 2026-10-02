from app.mockbank.db.database import SessionLocal
from app.mockbank.db.models import GenLedgerModel, TranTypeModel

GEN_LDGR_SEED = [
    ("100001", "Liability"),
    ("100002", "Income"),
]

TRAN_TYPE_SEED = [
    ("ATM Deposit", "Credit"),
    ("Contra ATM Deposit", "Debit"),
    ("ATM Withdrawal", "Debit"),
    ("Contra ATM Withdrawal", "Credit"),
    ("ATM Fees", "Debit"),
    ("Contra ATM Fees", "Credit"),
    ("POS Purchase", "Debit"),
    ("Contra POS Purchase", "Credit"),
    ("Cash Back", "Credit"),
    ("Contra Cash Back", "Debit"),
    ("Credit Interest", "Credit"),
    ("Contra Credit Interest", "Debit"),
    ("Fund Transfer To", "Debit"),
    ("Fund Transfer From", "Credit"),
]


def seed_gen_ledger() -> None:
    db = SessionLocal()
    try:
        for gl_account, gl_name in GEN_LDGR_SEED:
            if db.get(GenLedgerModel, gl_account) is None:
                db.add(GenLedgerModel(GL_ACCOUNT=gl_account, GL_NAME=gl_name))
        db.commit()
    finally:
        db.close()


def seed_tran_type() -> None:
    db = SessionLocal()
    try:
        for posting_name, posting_type in TRAN_TYPE_SEED:
            if db.get(TranTypeModel, posting_name) is None:
                db.add(TranTypeModel(POSTING_NAME=posting_name, POSTING_TYPE=posting_type))
        db.commit()
    finally:
        db.close()
