from datetime import timedelta

from core.auth.utils import create_access_token, verify_access_token


def test_access_token_round_trip_includes_expiry_claim():
    token = create_access_token({"sub": "user-1"}, expires_delta=timedelta(minutes=5))
    payload = verify_access_token(token)

    assert payload is not None
    assert payload["sub"] == "user-1"
    assert "exp" in payload
