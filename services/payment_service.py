"""Razorpay payment service for paid features."""

import os
import logging
import hmac
import hashlib

logger = logging.getLogger(__name__)

RESUME_OPTIMIZE_PRICE = int(os.environ.get("RESUME_PRICE_INR", 50))


def _key_id():
    return os.environ.get("RAZORPAY_KEY_ID", "")


def _key_secret():
    return os.environ.get("RAZORPAY_KEY_SECRET", "")


def is_configured() -> bool:
    return bool(_key_id() and _key_secret())


def _get_client():
    import razorpay
    return razorpay.Client(auth=(_key_id(), _key_secret()))


def create_order(amount_paise: int, receipt: str = "resume_opt") -> dict:
    """Create a Razorpay order. Returns order dict with 'id'."""
    client = _get_client()
    return client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1,
    })


def verify_payment(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify Razorpay payment signature."""
    msg = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(
        _key_secret().encode(), msg, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
