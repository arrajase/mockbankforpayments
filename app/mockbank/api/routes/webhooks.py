from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/test-receiver")
def test_receiver(payload: dict):
    """Dummy endpoint so the payments app can verify its webhook_url is reachable during local testing."""
    return {"received": True, "payload": payload}
