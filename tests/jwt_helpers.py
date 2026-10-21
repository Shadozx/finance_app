"""Standard-library JWT builder and reader for tests.

Tests must not depend on the JWT library the application uses, so a library swap leaves
them untouched and they stay an independent reference for the token format.
"""

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

HASH_BY_ALGORITHM = {
    "HS256": hashlib.sha256,
    "HS384": hashlib.sha384,
    "HS512": hashlib.sha512,
}

# An unsecured token: the signature segment is empty, but the dot before it stays
UNSECURED_ALGORITHM = "none"

DEFAULT_ALGORITHM = "HS256"

HEADER_INDEX = 0
PAYLOAD_INDEX = 1

BASE64_BLOCK_LENGTH = 4


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % BASE64_BLOCK_LENGTH))


def sign_jwt(signing_input: str, key: str, *, algorithm: str = DEFAULT_ALGORITHM) -> str:
    if algorithm == UNSECURED_ALGORITHM:
        return ""

    digest = hmac.new(key.encode(), signing_input.encode("ascii"), HASH_BY_ALGORITHM[algorithm])

    return b64url_encode(digest.digest())


def assemble_test_jwt(payload: bytes, key: str, *, algorithm: str = DEFAULT_ALGORITHM) -> str:
    """Build a token around raw payload bytes, so a test can put a non-JSON body in one."""
    header = json.dumps({"alg": algorithm, "typ": "JWT"}, separators=(",", ":")).encode()
    signing_input = f"{b64url_encode(header)}.{b64url_encode(payload)}"

    return f"{signing_input}.{sign_jwt(signing_input, key, algorithm=algorithm)}"


def encode_test_jwt(
    claims: Mapping[str, Any], key: str, *, algorithm: str = DEFAULT_ALGORITHM
) -> str:
    payload = json.dumps(claims, separators=(",", ":")).encode()

    return assemble_test_jwt(payload, key, algorithm=algorithm)


def _read_segment(token: str, index: int) -> dict[str, Any]:
    return json.loads(b64url_decode(token.split(".")[index]))


def read_jwt_header(token: str) -> dict[str, Any]:
    """Read the header without checking the signature."""
    return _read_segment(token, HEADER_INDEX)


def read_jwt_claims(token: str) -> dict[str, Any]:
    """Read the claims without checking the signature."""
    return _read_segment(token, PAYLOAD_INDEX)
