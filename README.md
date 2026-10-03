# MockBank

## https://mockbankforpayments.onrender.com

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
uv sync
uv run alembic upgrade head          # creates/updates the schema
uv run uvicorn main:app --reload
```

Requires a `.env` with `DATABASE_URL` (see `.env.example`). For plain-http local
development set `COOKIE_SECURE=false`.

Or run everything, including Postgres, with Docker:

```
docker compose up --build            # http://localhost:8000
```

### Database migrations

The schema is managed by Alembic (`migrations/`). The app no longer calls
`create_all`; Render runs `alembic upgrade head` before starting. Revision
`0001` is the original schema and skips tables that already exist, so an
existing database created by the old code upgrades in place.

### Tests

The tests need a **disposable** Postgres database (SQLite ignores
`SELECT … FOR UPDATE`, so the locking tests would prove nothing). The database
is wiped on every run.

```
docker compose up -d db
TEST_DATABASE_URL=postgresql+psycopg://mockbank:mockbank@localhost:5433/mockbank_test uv run pytest
```

Without `TEST_DATABASE_URL` every test is skipped.

### Issuing API keys

```
python -m app.mockbank.cli create-client --name paymentsapp-dev --owner <customer_id> [--webhook-url URL]
python -m app.mockbank.cli list-clients
python -m app.mockbank.cli set-webhook --name paymentsapp-dev --url URL
python -m app.mockbank.cli deactivate-client --name paymentsapp-dev
```

`create-client` prints the API key and webhook secret once; only the key's hash
is stored. `--owner` is the bank customer whose UPI IDs the client may pay
from (e.g. the "PaymentsApp" business customer that holds the escrow and
operating UPI IDs). A customer may hold several UPI IDs, each linked to one of
their accounts and protected by its own UPI PIN.

## The website

Customers sign up, log in (an `HttpOnly; Secure; SameSite=Lax` session cookie,
30-minute idle expiry) and manage their own accounts and UPI IDs. Every
website endpoint takes the customer from the session; another customer's
account or UPI ID answers `404`. `POST`/`PUT` calls must carry an `Origin`
header matching the bank's own site (`ALLOWED_ORIGINS`).

- **Post Transaction** ("ATM Deposit" etc.) creates test money, only in the
  customer's own accounts. The bank stamps the date and time.
- **Pending Requests** lists collect requests addressed to the customer's UPI
  IDs, to approve with the UPI PIN or decline.
- **App Permissions** lists consents, to allow with the UPI PIN, deny, or
  revoke later.

## Integrating a payments app: the gateway

A payments app only ever deals in **UPI IDs** (e.g. `someone@okmockbank`),
never internal account IDs. Each app is an **API client** with its own key.

### Authentication and permissions

```
x-api-key: mbk_<prefix>_<secret>
```

| Action | Allowed when |
|---|---|
| `pay`, `transactions` (move money out) | the UPI ID belongs to the client's owner customer |
| Take money from a customer | only via a collect request the customer approves with their UPI PIN |
| `balance`, `statement` | the UPI ID is the client's own, **or** `consent_id` names an ACTIVE consent covering that purpose (and, for statements, the date range) |
| `verify` | any UPI ID, at most 10 calls per minute per client |
| Transaction, collect and consent lookups, `/events` | only the client's own |

Anything else returns `403 NOT_PERMITTED` (or `CONSENT_REQUIRED`).

### Errors

Every error has one shape:

```json
{"error": {"code": "INSUFFICIENT_FUNDS", "message": "insufficient funds", "retryable": false}}
```

Decide whether to retry from `retryable`, not from the status code.

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Malformed request |
| `UNAUTHORIZED` | 401 | Missing/invalid API key, or not logged in |
| `UPI_NOT_FOUND` | 404 | Unknown UPI ID |
| `UPI_INACTIVE` | 422 | UPI ID is not ACTIVE |
| `TRANSACTION_NOT_FOUND`, `NOT_FOUND` | 404 | Nothing of yours with that ID |
| `INSUFFICIENT_FUNDS` | 422 | Recorded as a FAILED transaction (see below) |
| `CURRENCY_MISMATCH` | 422 | Sender, recipient and request currency differ |
| `SAME_UPI` | 422 | Sender and recipient are the same UPI ID or account |
| `NOT_PERMITTED` | 403 | The client may not act for that UPI ID |
| `CONSENT_REQUIRED` | 403 | No ACTIVE consent covering this read |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | Money-moving call without `Idempotency-Key` |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Same key, different request |
| `DUPLICATE_REFERENCE` | 409 | `client_reference` already used by this client |
| `COLLECT_EXPIRED`, `INVALID_STATE` | 409 | Collect request or consent no longer actionable |
| `PIN_INVALID` / `PIN_LOCKED` | 422 / 423 | Wrong UPI PIN; three wrong PINs lock it for 24 hours |
| `RATE_LIMITED` | 429 | Retryable |
| `INTERNAL_ERROR` / `SERVICE_UNAVAILABLE` | 500 / 503 | Retryable; use the same `Idempotency-Key` |

### Idempotency

`POST /upi/{upi_id}/pay`, `POST /upi/{upi_id}/transactions` and
`POST /collect-requests` require:

```
Idempotency-Key: <uuid>
```

- Same key, same body: the stored response is returned (header
  `Idempotent-Replayed: true`) and no money moves.
- Same key, different body: `409 IDEMPOTENCY_KEY_REUSED`.
- Keys are kept for 7 days.

The key, the balance change, both ledger legs and the outbox event are
committed in one database transaction, so a retry after a lost response can
never pay twice.

### Amounts, currency and dates

Amounts are integer minor units (`amount_cents`, paise for INR). `currency` is
required on every money request and must match both accounts. New accounts
default to INR. The bank sets `created_at` (UTC) and `tran_date` (the date in
IST); any `tran_date` you send is ignored.

### `POST /upi/{upi_id}/pay`

Pays from one of the client's own UPI IDs.

```json
{
  "recipient_upi_id": "someone@okmockbank",
  "amount_cents": 12000,
  "currency": "INR",
  "client_reference": "payout-8812",
  "narration": "Refund for order 8812"
}
```

`client_reference` is required, at most 64 characters, unique per client.
`narration` is optional, at most 100 characters.

**Response `200`**, a transaction record:

```json
{
  "transaction_id": "txn_…",
  "transfer_id": "trf_…",
  "status": "SUCCESS",
  "failure_reason": null,
  "tran_type": "Fund Transfer To",
  "posting_type": "Debit",
  "amount_cents": 12000,
  "currency": "INR",
  "upi_id": "escrow@okmockbank",
  "counterparty_upi_id": "someone@okmockbank",
  "sender_upi_id": "escrow@okmockbank",
  "recipient_upi_id": "someone@okmockbank",
  "client_reference": "payout-8812",
  "narration": "Refund for order 8812",
  "balance_after_cents": 88000,
  "created_at": "2026-10-03T09:15:02.123456Z",
  "tran_date": "2026-10-03"
}
```

**Insufficient funds** is a recorded outcome: `422` with
`{"error": {...INSUFFICIENT_FUNDS...}, "transaction": {...status: "FAILED"...}}`.
The failed transaction can be looked up by its reference.

### `POST /upi/{upi_id}/transactions`

Single-account posting (`ATM Deposit`, `ATM Withdrawal`, `ATM Fees`,
`POS Purchase`, `Cash Back`, `Credit Interest`) on one of the client's own UPI
IDs. The body has `tran_type`, `amount_cents`, `currency`, `client_reference`
and optional `narration`. It returns a transaction record.

### Status lookup

When a call's outcome is unknown (timeout, `5xx`), ask:

- `GET /transactions/{transaction_id}`
- `GET /transactions?client_reference=payout-8812`

Both return the transaction record (`SUCCESS`, or `FAILED` with
`failure_reason`), or `404 TRANSACTION_NOT_FOUND` if the bank never recorded
it. Only the calling client's own transactions are visible.

### `GET /upi/{upi_id}/verify`

Checks a UPI ID without revealing its balance. Rate limited to 10 calls per
minute per client.

```json
{"upi_id": "someone@okmockbank", "account_holder_name": "Jane Doe", "currency": "INR", "status": "ACTIVE"}
```

### `GET /upi/{upi_id}/balance[?consent_id=…]`

```json
{"upi_id": "…", "owner_name": "…", "account_type": "checking", "balance_cents": 15000, "currency": "INR"}
```

### `GET /upi/{upi_id}/statement?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=100&cursor=…[&consent_id=…]`

Successful postings, newest first:

```json
{"items": [/* transaction records */], "next_cursor": "…or null"}
```

Pass `next_cursor` back as `cursor` for the next page. `limit` is at most 500.
With a consent, `from`/`to` default to the consented range and may not go
outside it. `client_reference` is only shown on lines your client created.

### Collect requests: taking money from a customer

`POST /collect-requests` (requires `Idempotency-Key`):

```json
{
  "payer_upi_id": "someone@okmockbank",
  "payee_upi_id": "escrow@okmockbank",
  "amount_cents": 50000,
  "currency": "INR",
  "client_reference": "topup-311",
  "note": "Add money to wallet",
  "expires_in_seconds": 300
}
```

`payee_upi_id` must be the client's own. `expires_in_seconds` is at most 900.
It returns `201` with `collect_id`, `status: "PENDING"` and `expires_at`.

The customer approves on the website's **Pending Requests** page with their
UPI PIN. The app never sees the PIN. Approval runs the transfer in one
commit:

| Status | Meaning |
|---|---|
| `PENDING` | Waiting for the customer |
| `SUCCESS` | Paid; `transaction_id` is set (its `client_reference` is the collect's) |
| `FAILED` | `failure_reason`, e.g. `INSUFFICIENT_FUNDS` |
| `DECLINED` | The customer said no |
| `EXPIRED` | Not acted on in time (checked on read and by a periodic sweep) |

`GET /collect-requests/{collect_id}` returns the current state. Every change
also produces a `collect_request.updated` event.

### Consents: linking and statements

`POST /consents`:

```json
{
  "upi_id": "someone@okmockbank",
  "purposes": ["LINK", "STATEMENT", "BALANCE"],
  "statement_from": "2026-04-01",
  "statement_to": "2026-09-30",
  "expires_at": "2027-10-03T00:00:00Z"
}
```

`statement_from`/`statement_to` are required with `STATEMENT`. The call
returns `201` with `consent_id` and `status: "PENDING"`. The customer allows
it on the **App Permissions** page with their UPI PIN, which makes it
`ACTIVE`, and can later revoke it (`REVOKED`). Other states are `REJECTED` and
`EXPIRED`. An ACTIVE `LINK` consent is the bank's confirmation that the
customer owns the UPI ID.

`GET /consents/{consent_id}` returns the current state. Changes produce
`consent.updated` events.

### Webhooks and events

Events:

- `transaction.posted`: any successful movement on an account owned by the
  client's owner customer, including ones the client didn't make (e.g. a
  website deposit into escrow).
- `collect_request.updated`
- `consent.updated`

Payload (the request body):

```json
{"event_id": "evt_…", "type": "transaction.posted", "created_at": "…Z", "data": { /* record */ }}
```

Headers:

```
X-MockBank-Event-Id: evt_…
X-MockBank-Signature: t=<unix seconds>,v1=<hex>
```

`v1 = HMAC_SHA256(webhook_secret, f"{t}.{raw_body}")`. Verify it against the
raw bytes before parsing, and reject stale `t` values.

Events are written in the same commit as the change they describe and
delivered **at least once**. Respond `2xx` to acknowledge. Failed deliveries
are retried after 1 minute, 5 minutes, 30 minutes and 2 hours, then every
2 hours, giving up 24 hours after the event. De-duplicate on `event_id`.

Render's free tier sleeps, which stops delivery. Poll to catch up:

```
GET /events?after=<last event_id you processed>&limit=100   →   {"items": [/* events, oldest first */]}
```

### Sandbox triggers

With `SANDBOX_TRIGGERS=true`, the last two digits of `amount_cents` force a
failure, so the app's handling of unknown outcomes can be tested:

| Amount ends in | Behaviour |
|---|---|
| `…13` | Moves the money, then waits 30 seconds before answering (client times out) |
| `…14` | Moves the money, then returns `500` (no confirmation of a payment that succeeded) |
| `…15` | Returns `503` without moving any money |
| `…16` | A collect request expires immediately |

Retrying `…14` with the same `Idempotency-Key` returns the stored success.
