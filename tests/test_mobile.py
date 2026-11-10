"""Mobile numbers: required at signup, added on the profile, linked to a UPI ID and looked up by apps."""

import uuid

from fastapi.testclient import TestClient

from tests.app_helpers import new_mobile

ORIGIN = "http://testserver"


def _signup(**overrides):
    from main import app

    web = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
    login_id = f"m-{uuid.uuid4().hex[:6]}"
    body = {"first_name": "Mo", "last_name": "Bile", "login_id": login_id, "mobile_number": new_mobile(),
            "password": "pw", "confirm_password": "pw", **overrides}
    return web, login_id, web.post("/auth/signup", json=body)


def _lookup(setup, mobile_number):
    return setup.app.post("/upi/lookup", {"mobile_number": mobile_number}, key=None)


def _mobile(customer) -> str:
    return customer.web.get("/me").json()["mobile_number"]


# ---------- signup and profile ----------

def test_signup_requires_a_valid_mobile_number(app_client):
    from main import app

    web = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
    r = web.post("/auth/signup", json={"first_name": "A", "last_name": "B", "login_id": "nomobile",
                                       "password": "pw", "confirm_password": "pw"})
    assert r.status_code == 422 and "mobile_number" in r.json()["error"]["message"]

    for bad in ("12345", "5876543210", "98765432101", "98765abcde"):
        _, _, r = _signup(mobile_number=bad)
        assert r.status_code == 422, bad
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_signup_normalises_and_stores_the_mobile_number(app_client):
    web, login_id, r = _signup(mobile_number="+91 98765-43210")
    assert r.status_code == 200, r.text
    assert r.json()["mobile_number"] == "9876543210"
    web.post("/auth/login", json={"login_id": login_id, "password": "pw"})
    assert web.get("/me").json()["mobile_number"] == "9876543210"


def test_mobile_number_is_unique_across_customers(app_client):
    _, _, r = _signup(mobile_number="9876543210")
    assert r.status_code == 200
    _, _, r = _signup(mobile_number="09876543210")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_existing_customer_without_mobile_adds_one_on_profile(bank, db):
    from app.mockbank.db.models import CustomerModel

    ravi = bank.customer("Ravi")
    db.get(CustomerModel, ravi.customer_id).mobile_number = None  # as if they signed up before it was required
    db.commit()
    assert ravi.web.get("/me").json()["mobile_number"] is None

    r = ravi.web.put("/me/mobile", json={"mobile_number": "8123456789"})
    assert r.status_code == 200, r.text
    assert ravi.web.get("/me").json()["mobile_number"] == "8123456789"

    assert ravi.web.put("/me/mobile", json={"mobile_number": "123"}).status_code == 422


def test_cannot_take_another_customers_mobile_number(bank):
    ravi, asha = bank.customer("Ravi"), bank.customer("Asha")
    r = asha.web.put("/me/mobile", json={"mobile_number": _mobile(ravi)})
    assert r.status_code == 409
    # Saving your own number again is fine.
    assert ravi.web.put("/me/mobile", json={"mobile_number": _mobile(ravi)}).status_code == 200


# ---------- linking a UPI ID ----------

def test_link_mobile_to_upi_moves_between_own_upi_ids(bank):
    ravi = bank.customer("Ravi", handle=f"ravi{uuid.uuid4().hex[:6]}")
    second = ravi.web.post("/upi", json={"handle": f"ravi2{uuid.uuid4().hex[:6]}", "account_id": ravi.account_id,
                                         "upi_pin": "1234"}).json()["upi_id"]
    assert all(not u["mobile_linked"] for u in ravi.web.get("/upi").json())

    r = ravi.web.put(f"/upi/{ravi.upi_id}/mobile-link", json={"linked": True})
    assert r.status_code == 200, r.text
    assert r.json()["mobile_linked"] is True

    assert ravi.web.put(f"/upi/{second}/mobile-link", json={"linked": True}).status_code == 200
    linked = {u["upi_id"]: u["mobile_linked"] for u in ravi.web.get("/upi").json()}
    assert linked == {ravi.upi_id: False, second: True}

    assert ravi.web.put(f"/upi/{second}/mobile-link", json={"linked": False}).json()["mobile_linked"] is False


def test_link_needs_a_mobile_number_and_an_own_upi_id(bank, db):
    from app.mockbank.db.models import CustomerModel

    ravi = bank.customer("Ravi", handle=f"ravi{uuid.uuid4().hex[:6]}")
    asha = bank.customer("Asha", handle=f"asha{uuid.uuid4().hex[:6]}")
    assert asha.web.put(f"/upi/{ravi.upi_id}/mobile-link", json={"linked": True}).status_code == 404

    db.get(CustomerModel, ravi.customer_id).mobile_number = None
    db.commit()
    r = ravi.web.put(f"/upi/{ravi.upi_id}/mobile-link", json={"linked": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------- gateway lookup ----------

def test_lookup_finds_the_linked_upi_id(setup):
    ravi = setup.ravi
    ravi.web.put(f"/upi/{ravi.upi_id}/mobile-link", json={"linked": True})

    r = _lookup(setup, _mobile(ravi))
    assert r.status_code == 200, r.text
    assert r.json() == {"upi_id": ravi.upi_id, "account_holder_name": "Ravi Test", "currency": "INR", "status": "ACTIVE"}
    # Any accepted spelling of the number finds it.
    assert _lookup(setup, f"+91-{_mobile(ravi)}").json()["upi_id"] == ravi.upi_id


def test_lookup_follows_a_changed_mobile_number(setup):
    ravi = setup.ravi
    ravi.web.put(f"/upi/{ravi.upi_id}/mobile-link", json={"linked": True})
    old = _mobile(ravi)
    ravi.web.put("/me/mobile", json={"mobile_number": new_mobile()})

    assert _lookup(setup, old).status_code == 422
    assert _lookup(setup, _mobile(ravi)).json()["upi_id"] == ravi.upi_id


def test_lookup_rejects_a_number_with_no_linked_upi_id(setup):
    # Registered but not linked.
    r = _lookup(setup, _mobile(setup.ravi))
    assert r.status_code == 422
    assert r.json()["error"] == {"code": "VALIDATION_ERROR", "message": "mobile number is not linked to any UPI ID",
                                 "retryable": False}
    # Not registered at all: the same answer, so a caller cannot tell the two apart.
    assert _lookup(setup, "6000000000").json()["error"]["code"] == "VALIDATION_ERROR"
    # Unlinking takes effect straight away.
    setup.ravi.web.put(f"/upi/{setup.ravi.upi_id}/mobile-link", json={"linked": True})
    setup.ravi.web.put(f"/upi/{setup.ravi.upi_id}/mobile-link", json={"linked": False})
    assert _lookup(setup, _mobile(setup.ravi)).status_code == 422


def test_lookup_validates_the_number_and_needs_an_api_key(setup, app_client):
    assert _lookup(setup, "12345").status_code == 422
    r = app_client.post("/upi/lookup", json={"mobile_number": _mobile(setup.ravi)})
    assert r.status_code == 401


def test_lookup_shares_the_verify_rate_limit(setup):
    from app.mockbank.core.config import VERIFY_RATE_LIMIT_PER_MINUTE

    for _ in range(VERIFY_RATE_LIMIT_PER_MINUTE):
        setup.app.get(f"/upi/{setup.ravi.upi_id}/verify")
    r = _lookup(setup, _mobile(setup.ravi))
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
