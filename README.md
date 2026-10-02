# MockBank

## Why this project exists

MockBank is a mock/test-double bank — a standalone FastAPI service plus a small
browser UI (signup, login, accounts, transaction posting, UPI) — built so a
separate **payments app** can be developed and tested against realistic bank
behavior without touching a real banking API. It models customers, accounts,
double-entry transaction posting against a general ledger, and UPI IDs as the
public-facing identifier a payments app uses to interact with a customer's
account.

It is not a real bank and holds no real money. All data lives in a single
Postgres (Neon) database.

## Running locally

```
uv run uvicorn main:app --reload
```

Requires a `.env` with `DATABASE_URL`, `BANK_API_KEY`, and
`WEBHOOK_SIGNING_SECRET` (see `.env.example`).

## Integrating a 3rd-party payments app: the `/upi` gateway

A payments app should **never need to know a customer's internal
`account_id`** — the only identifier it deals with is the customer's **UPI
ID** (e.g. `someone@okmockbank`). Resolving a UPI ID to its linked account,
and everything that touches money, happens server-side.

> Note: `POST /upi`, `GET /upi`, and `PUT /upi/{upi_id}` are separate,
> unauthenticated endpoints used by MockBank's own website for a customer to
> create/view/edit their own UPI ID. They are not part of the 3rd-party
> integration surface below.

### Authentication

Every endpoint below requires an `x-api-key` header matching the `BANK_API_KEY`
configured in MockBank's `.env`. Missing the header returns `422`; a wrong
value returns `401`.

```
x-api-key: <BANK_API_KEY>
```

### `GET /upi/{upi_id}/balance`

Returns the current balance of the account linked to a UPI ID.

**Response `200`**
```json
{
  "upi_id": "someone@okmockbank",
  "owner_name": "Jane Doe",
  "account_type": "checking",
  "balance_cents": 15000,
  "currency": "USD"
}
```

**Errors:** `404` if the UPI ID doesn't exist.

### `GET /upi/{upi_id}/statement`

Returns the transaction history for the account linked to a UPI ID, newest
first.

**Response `200`**
```json
[
  {
    "transaction_id": "txn_...",
    "tran_type": "ATM Deposit",
    "posting_type": "Credit",
    "amount": 15000,
    "tran_date": "2026-10-02"
  }
]
```

**Errors:** `404` if the UPI ID doesn't exist.

### `POST /upi/{upi_id}/transactions`

Posts a single-account transaction (deposit, withdrawal, fee, etc.) against
the account linked to a UPI ID. The debit/credit direction and the matching
general-ledger posting are determined server-side — do not send a
`posting_type`.

**Request body**
```json
{
  "tran_type": "ATM Deposit",
  "amount_cents": 15000,
  "tran_date": "2026-10-02"
}
```

`tran_type` must be one of:
`ATM Deposit`, `ATM Withdrawal`, `ATM Fees`, `POS Purchase`, `Cash Back`, `Credit Interest`

**Response `200`** — same shape as a statement entry (see above).

**Errors:** `404` unknown UPI ID · `400` insufficient funds for a debit type
(no balance change, nothing is written) · `422` invalid `tran_type` or
non-positive `amount_cents`.

### `POST /upi/{upi_id}/pay`

Transfers money from the UPI ID in the path (sender) to another UPI ID
(recipient). Debits the sender's account, credits the recipient's — both
sides land in `TRANSACTION_HISTORY` as `Fund Transfer To` (sender) and
`Fund Transfer From` (recipient).

**Request body**
```json
{
  "recipient_upi_id": "someoneelse@okmockbank",
  "amount_cents": 12000,
  "tran_date": "2026-10-02"
}
```

**Response `200`**
```json
{
  "transaction_id": "txn_...",
  "sender_upi_id": "someone@okmockbank",
  "recipient_upi_id": "someoneelse@okmockbank",
  "amount": 12000,
  "tran_date": "2026-10-02"
}
```

**Errors:** `404` either UPI ID doesn't exist · `400` sender and recipient are
the same UPI ID, or sender has insufficient funds (no balance change on
either side) · `422` non-positive `amount_cents`.

### Amounts

All `amount_cents` values are integer cents (e.g. `15000` = `150.00`), to
avoid floating-point rounding issues. Responses echo amounts back the same
way.
