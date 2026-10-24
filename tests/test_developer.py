"""Self-service API keys on the website's Developer page."""

import uuid


def _register(customer, name=None, webhook_url=None):
    body = {"name": name or f"app-{uuid.uuid4().hex[:6]}"}
    if webhook_url is not None:
        body["webhook_url"] = webhook_url
    return customer.web.post("/me/api-clients", json=body)


def _gateway(app_client, api_key, path):
    return app_client.get(path, headers={"x-api-key": api_key})


def test_registered_key_works_for_own_upi_only(app_client, bank):
    biz = bank.customer("Biz", deposit_cents=10_000, handle=f"biz{uuid.uuid4().hex[:6]}")
    ravi = bank.customer("Ravi", handle=f"ravi{uuid.uuid4().hex[:6]}")

    r = _register(biz, "paymentsapp-dev", "https://app.example/hooks")
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["api_key"].startswith(created["key_hint"].removesuffix("..."))
    assert created["webhook_secret"].startswith("whsec_")
    assert created["webhook_url"] == "https://app.example/hooks"

    key = created["api_key"]
    assert _gateway(app_client, key, f"/upi/{biz.upi_id}/balance").json()["balance_cents"] == 10_000
    assert _gateway(app_client, key, f"/upi/{ravi.upi_id}/balance").json()["error"]["code"] == "CONSENT_REQUIRED"

    listed = biz.web.get("/me/api-clients").json()
    assert [c["name"] for c in listed] == ["paymentsapp-dev"]
    assert "api_key" not in listed[0] and "webhook_secret" not in listed[0]


def test_other_customers_cannot_see_or_change_an_app(bank):
    biz = bank.customer("Biz")
    mallory = bank.customer("Mallory")
    client_id = _register(biz).json()["client_id"]

    assert mallory.web.get("/me/api-clients").json() == []
    assert mallory.web.put(f"/me/api-clients/{client_id}", json={"active": False}).status_code == 404
    assert mallory.web.post(f"/me/api-clients/{client_id}/rotate-key").status_code == 404
    assert mallory.web.get(f"/me/api-clients/{client_id}/webhook-secret").status_code == 404


def test_rotate_key_retires_the_old_key(app_client, bank):
    biz = bank.customer("Biz", handle=f"biz{uuid.uuid4().hex[:6]}")
    created = _register(biz).json()
    old_key = created["api_key"]

    rotated = biz.web.post(f"/me/api-clients/{created['client_id']}/rotate-key").json()
    assert rotated["api_key"] != old_key
    assert _gateway(app_client, old_key, f"/upi/{biz.upi_id}/balance").status_code == 401
    assert _gateway(app_client, rotated["api_key"], f"/upi/{biz.upi_id}/balance").status_code == 200


def test_deactivate_and_reactivate(app_client, bank):
    biz = bank.customer("Biz", handle=f"biz{uuid.uuid4().hex[:6]}")
    created = _register(biz).json()
    url = f"/me/api-clients/{created['client_id']}"

    assert biz.web.put(url, json={"active": False}).json()["active"] is False
    assert _gateway(app_client, created["api_key"], f"/upi/{biz.upi_id}/balance").status_code == 401
    assert biz.web.put(url, json={"active": True}).json()["active"] is True
    assert _gateway(app_client, created["api_key"], f"/upi/{biz.upi_id}/balance").status_code == 200


def test_webhook_url_and_secret(bank):
    biz = bank.customer("Biz")
    created = _register(biz).json()
    url = f"/me/api-clients/{created['client_id']}"

    assert biz.web.put(url, json={"webhook_url": "https://app.example/new"}).json()["webhook_url"] == "https://app.example/new"
    assert biz.web.put(url, json={"active": True}).json()["webhook_url"] == "https://app.example/new"  # untouched
    assert biz.web.put(url, json={"webhook_url": None}).json()["webhook_url"] is None
    assert biz.web.put(url, json={"webhook_url": "ftp://nope"}).status_code == 422

    assert biz.web.get(f"{url}/webhook-secret").json()["webhook_secret"] == created["webhook_secret"]
    new_secret = biz.web.post(f"{url}/rotate-webhook-secret").json()["webhook_secret"]
    assert new_secret != created["webhook_secret"]
    assert biz.web.get(f"{url}/webhook-secret").json()["webhook_secret"] == new_secret


def test_names_are_validated_and_unique(bank):
    biz = bank.customer("Biz")
    other = bank.customer("Other")
    assert _register(biz, "ab").status_code == 422
    assert _register(biz, "shared-name").status_code == 201
    r = _register(other, "shared-name")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_registered_app_appears_in_other_customers_app_access(bank):
    biz = bank.customer("Biz")
    ravi = bank.customer("Ravi", handle=f"ravi{uuid.uuid4().hex[:6]}")
    _register(biz, "paymentsapp-dev")
    assert [r["client_name"] for r in ravi.web.get("/me/app-access").json()] == ["paymentsapp-dev"]


def test_portal_needs_login_and_same_origin(app_client, bank):
    from fastapi.testclient import TestClient

    from main import app

    assert TestClient(app, base_url="http://testserver").get("/me/api-clients").status_code == 401
    biz = bank.customer("Biz")
    biz.web.headers.pop("Origin", None)
    r = biz.web.post("/me/api-clients", json={"name": "csrf-app"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
