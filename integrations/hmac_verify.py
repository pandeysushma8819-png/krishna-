# integrations/hmac_verify.py
from __future__ import annotations
import hmac, hashlib, json

def verify_hmac(body: bytes, header_value: str | None, secret: str | None, allow_plain: bool = False) -> tuple[bool, str]:
    """
    HMAC-SHA256 verify using header hex digest.
    Fallback (if allow_plain=True): accept {"secret": "..."} in JSON body.
    """
    secret = (secret or "").strip()
    if not secret:
        return (True, "no_secret_configured")  # nothing to verify

    if header_value:
        try:
            digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            # constant-time compare
            if hmac.compare_digest(digest, header_value.strip().lower()):
                return (True, "hmac_ok")
            else:
                return (False, "hmac_mismatch")
        except Exception as e:
            return (False, f"hmac_error:{e}")

    # No signature header
    if allow_plain:
        try:
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, str):
                payload = json.loads(payload)
            if str(payload.get("secret", "")).strip() == secret:
                return (True, "plain_secret_ok")
            return (False, "plain_secret_mismatch")
        except Exception as e:
            return (False, f"plain_secret_parse_error:{e}")

    return (False, "missing_signature_header")
