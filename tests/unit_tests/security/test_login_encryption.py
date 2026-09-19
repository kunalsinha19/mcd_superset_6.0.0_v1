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
"""Login password encryption (audit #2/#4). Pure crypto -- no app needed."""
from __future__ import annotations

import base64
import json
import os

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from superset.security.login_encryption import (
    decrypt_login_password,
    server_public_key,
)

SECRET = "unit-test-secret-key"
NONCE = "nonce-abc123"


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encrypt_like_browser(password: str, secret: str = SECRET, nonce: str = NONCE) -> str:
    """Mirror of superset-frontend/src/utils/passwordEncryption.ts."""
    peer = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b64u_decode(server_public_key(secret))
    )
    client_key = ec.generate_private_key(ec.SECP256R1())
    shared = client_key.exchange(ec.ECDH(), peer)
    salt, iv = os.urandom(16), os.urandom(12)
    key = HKDF(hashes.SHA256(), 32, salt, b"superset-login-msg-v1").derive(shared)
    ciphertext = AESGCM(key).encrypt(
        iv, json.dumps({"p": password, "n": nonce}).encode(), None
    )
    client_pub = client_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    return ".".join(["v1"] + [b64u(x) for x in (client_pub, salt, iv, ciphertext)])


def test_round_trip_including_awkward_characters() -> None:
    password = "P@ss'w\"0rd\\ é中\U0001f511"
    blob = encrypt_like_browser(password)
    assert decrypt_login_password(SECRET, blob, NONCE) == password


def test_blob_does_not_contain_the_password() -> None:
    blob = encrypt_like_browser("SuperSecret123!")
    assert "SuperSecret" not in blob


def test_two_encryptions_of_the_same_password_differ() -> None:
    assert encrypt_like_browser("x") != encrypt_like_browser("x")


@pytest.mark.parametrize("nonce", ["another-nonce", "", None])
def test_wrong_or_missing_nonce_is_rejected(nonce: str | None) -> None:
    assert decrypt_login_password(SECRET, encrypt_like_browser("pw"), nonce) is None


def test_different_secret_key_cannot_decrypt() -> None:
    assert decrypt_login_password("other-secret", encrypt_like_browser("pw"), NONCE) is None


def test_tampered_ciphertext_is_rejected() -> None:
    head, *rest = encrypt_like_browser("pw").split(".")
    rest[-1] = b64u(b"x" + b64u_decode(rest[-1])[1:])
    assert decrypt_login_password(SECRET, ".".join([head] + rest), NONCE) is None


@pytest.mark.parametrize(
    "garbage", ["", "v1", "v1.a.b.c.d", "v2.a.b.c.d", "not a blob", "x" * 5000, "....."]
)
def test_garbage_is_rejected_without_raising(garbage: str) -> None:
    assert decrypt_login_password(SECRET, garbage, NONCE) is None


def test_non_string_password_payload_is_rejected() -> None:
    peer = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b64u_decode(server_public_key(SECRET))
    )
    client_key = ec.generate_private_key(ec.SECP256R1())
    salt, iv = os.urandom(16), os.urandom(12)
    key = HKDF(hashes.SHA256(), 32, salt, b"superset-login-msg-v1").derive(
        client_key.exchange(ec.ECDH(), peer)
    )
    ciphertext = AESGCM(key).encrypt(
        iv, json.dumps({"p": 12345, "n": NONCE}).encode(), None
    )
    pub = client_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    blob = ".".join(["v1"] + [b64u(x) for x in (pub, salt, iv, ciphertext)])
    assert decrypt_login_password(SECRET, blob, NONCE) is None


def test_server_key_is_stable_per_secret_and_differs_between_secrets() -> None:
    assert server_public_key(SECRET) == server_public_key(SECRET)
    assert server_public_key(SECRET) != server_public_key("another")
    assert len(b64u_decode(server_public_key(SECRET))) == 65  # uncompressed P-256
