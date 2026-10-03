"""Outbox events, signed delivery with retries, and polling."""

import hashlib
import hmac
import json
from datetime import timedelta

import httpx

from tests.app_helpers import parse_signature


def _deliver(db, handler):
    from app.mockbank.services import events

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        return events.deliver_due_events(db, http=http)


def test_payment_events_are_signed_and_delivered(bank, db, setup):
    from app.mockbank.db.models import ApiClientModel

    db.query(ApiClientModel).filter_by(client_id=setup.app.client_id).update({"webhook_url": "https://app.example/hooks"})
    db.commit()
    setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 1_000, reference="hooked")

    received = []

    def handler(request: httpx.Request):
        received.append(request)
        return httpx.Response(200)

    assert _deliver(db, handler) == 1
    request = received[0]
    raw = request.content.decode()
    t, v1 = parse_signature(request.headers["X-MockBank-Signature"])
    expected = hmac.new(setup.app.webhook_secret.encode(), f"{t}.{raw}".encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(v1, expected)

    event = json.loads(raw)
    assert request.headers["X-MockBank-Event-Id"] == event["event_id"]
    assert event["type"] == "transaction.posted"
    assert event["data"]["client_reference"] == "hooked"
    assert set(event) == {"event_id", "type", "created_at", "data"}
    assert _deliver(db, handler) == 0  # delivered once


def test_movements_the_client_did_not_make_are_reported(bank, setup):
    """A website deposit into the escrow account still produces transaction.posted for the owning client."""
    r = setup.escrow.web.post("/transactions", json={"account_id": setup.escrow.account_id, "tran_type": "ATM Deposit", "amount_cents": 777})
    assert r.status_code == 200
    items = setup.app.get("/events").json()["items"]
    assert [e["type"] for e in items] == ["transaction.posted"]
    assert items[0]["data"]["amount_cents"] == 777
    assert items[0]["data"]["client_reference"] is None


def test_failed_delivery_is_retried_on_schedule(bank, db, setup):
    from app.mockbank.db.models import ApiClientModel, OutboxEventModel

    db.query(ApiClientModel).filter_by(client_id=setup.app.client_id).update({"webhook_url": "https://app.example/down"})
    db.commit()
    setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 1_000)

    assert _deliver(db, lambda request: httpx.Response(503)) == 1
    event = db.query(OutboxEventModel).one()
    assert event.delivery_status == "PENDING" and event.attempts == 1 and event.last_error == "HTTP 503"
    assert timedelta(seconds=55) < event.next_attempt_at - event.created_at < timedelta(seconds=70)
    assert _deliver(db, lambda request: httpx.Response(200)) == 0  # not due yet

    # past the 24 hour window: give up
    event.created_at -= timedelta(hours=25)
    event.next_attempt_at -= timedelta(hours=25)
    db.commit()
    _deliver(db, lambda request: httpx.Response(503))
    db.refresh(event)
    assert event.delivery_status == "FAILED"


def test_events_are_committed_with_the_money_and_pollable(bank, setup):
    setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100, reference="e1")
    setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 999_999_999, reference="e-fail")  # FAILED: no event
    setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 200, reference="e2")

    items = setup.app.get("/events").json()["items"]
    assert [e["data"]["client_reference"] for e in items] == ["e1", "e2"]
    after = setup.app.get("/events", after=items[0]["event_id"]).json()["items"]
    assert [e["event_id"] for e in after] == [items[1]["event_id"]]


def test_collect_and_consent_changes_emit_events(setup):
    body = {"payer_upi_id": setup.ravi.upi_id, "payee_upi_id": setup.escrow.upi_id, "amount_cents": 100,
            "currency": "INR", "client_reference": "ev-col"}
    collect = setup.app.post("/collect-requests", body).json()
    setup.ravi.web.post(f"/me/collect-requests/{collect['collect_id']}/decline")
    types = [e["type"] for e in setup.app.get("/events").json()["items"]]
    assert types == ["collect_request.updated"]


def test_events_are_per_client(bank, setup):
    setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100)
    stranger = bank.api_client(bank.customer("Stranger").customer_id)
    assert stranger.get("/events").json()["items"] == []
