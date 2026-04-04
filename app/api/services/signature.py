"""HMAC-SHA256 webhook signature verification."""
import hashlib
import hmac


def verify_zalo_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verify the HMAC-SHA256 signature of the raw webhook body.

    Args:
        raw_body: The raw bytes of the request body.
        signature: The X-Zalo-Signature header value.
        secret: The Zalo webhook secret for the app.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not signature or not secret:
        return False

    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
