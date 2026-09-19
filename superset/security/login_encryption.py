# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Application-layer encryption of the login password (audit findings #2 and
#4, "Weak Algorithm" / "Password travel in clear text").

The browser encrypts the password to the server's public key before it
leaves the page, so a captured or proxied login request carries ciphertext,
never the password. The server decrypts back to the raw password and hands
it to the *existing* scrypt verification -- stored hashes, existing users
and every other password path are untouched, so nothing needs migrating and
nobody is locked out. (Sending a client-side *hash* instead would have
forced exactly that: the server could no longer verify any existing account.)

Scheme (all primitives are native Web Crypto on the browser side):
  * ECDH over P-256 between an ephemeral client key and the server key
  * HKDF-SHA256 (random per-message salt) to derive an AES-256-GCM key
  * AES-GCM over {"p": <password>, "n": <server nonce>}
The nonce is issued with the CAPTCHA (see login_captcha.py), kept in the
server-side session and consumed on first use, so a captured ciphertext
cannot be replayed even within its own session.

The server key is derived deterministically from SECRET_KEY, so every
gunicorn worker agrees on it with no key file, DB row or rollout step.
Whoever holds SECRET_KEY can already forge sessions, so this adds no new
secret to protect. This is defence in depth *on top of* TLS, not a
replacement for it.

Wire format: "v1.<client_pub>.<salt>.<iv>.<ciphertext+tag>", each part
unpadded base64url.
"""
from __future__ import annotations

import base64
import functools
import hmac
import json
import logging

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

logger = logging.getLogger(__name__)

# Order of the NIST P-256 group; used to map the HKDF output onto a valid
# private scalar in [1, n-1].
_P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_SERVER_KEY_INFO = b"superset-login-enc-v1"
_MESSAGE_KEY_INFO = b"superset-login-msg-v1"
_VERSION = "v1"
MAX_ENCRYPTED_LEN = 2048


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@functools.lru_cache(maxsize=4)
def _server_private_key(secret_key: str) -> ec.EllipticCurvePrivateKey:
    seed = HKDF(
        algorithm=hashes.SHA256(),
        length=48,
        salt=None,
        info=_SERVER_KEY_INFO,
    ).derive(secret_key.encode("utf-8"))
    scalar = int.from_bytes(seed, "big") % (_P256_ORDER - 1) + 1
    return ec.derive_private_key(scalar, ec.SECP256R1())


def server_public_key(secret_key: str) -> str:
    """Server public key as unpadded base64url of the 65-byte uncompressed
    point -- the format Web Crypto's importKey('raw', ...) expects."""
    raw = (
        _server_private_key(secret_key)
        .public_key()
        .public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    )
    return _b64u_encode(raw)


def decrypt_login_password(
    secret_key: str, blob: str | None, expected_nonce: str | None
) -> str | None:
    """Return the plaintext password, or None if the blob is malformed,
    tampered with, or carries anything other than the nonce this session
    was issued. Deliberately gives the caller no reason for the failure."""
    if not blob or not expected_nonce or len(blob) > MAX_ENCRYPTED_LEN:
        return None
    try:
        version, client_pub, salt, iv, ciphertext = blob.split(".")
        if version != _VERSION:
            return None
        peer = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), _b64u_decode(client_pub)
        )
        shared = _server_private_key(secret_key).exchange(ec.ECDH(), peer)
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_b64u_decode(salt),
            info=_MESSAGE_KEY_INFO,
        ).derive(shared)
        plaintext = AESGCM(key).decrypt(
            _b64u_decode(iv), _b64u_decode(ciphertext), None
        )
        data = json.loads(plaintext)
        if not hmac.compare_digest(str(data.get("n", "")), expected_nonce):
            return None
        password = data.get("p")
        return password if isinstance(password, str) else None
    except Exception:  # pylint: disable=broad-except
        logger.debug("Login password decryption failed", exc_info=True)
        return None
