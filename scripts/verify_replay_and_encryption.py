#!/usr/bin/env python
"""Verifies the two fixes for audit findings #1 / #2 / #4 against real code.

PART 1 (offline, no server needed)
  Loads superset/security/login_encryption.py and checks that
    * a password encrypted the way the browser does it decrypts correctly
    * a Web Crypto (Node) encryption -- same primitives as a browser --
      decrypts correctly, i.e. the TypeScript helper and the Python server
      really interoperate
    * a wrong nonce, a tampered blob and a garbage blob are all rejected

PART 2 (online, needs a running server and a real account)
    export SUPERSET_URL=http://localhost:8089
    export SUPERSET_TEST_USER=<username>
    export SUPERSET_TEST_PASSWORD=<password>
  Reproduces the Burp PoC from the audit and checks the fixes:
    * login with an ENCRYPTED password works, and the request body sent
      contains no plaintext password
    * replaying the exact same encrypted login request is rejected
    * a session cookie captured before logout is REJECTED after logout
      (this is the "Response Replay" bug)

PART 3 (optional; the test account must have the Admin role)
    export SUPERSET_TEST_IS_ADMIN=1
  Checks that an admin can create and update a user with an ENCRYPTED
  password via /api/v1/security/users/ and that it really is stored.

Run:  python scripts/verify_replay_and_encryption.py
"""
from __future__ import annotations

import base64
import http.cookiejar
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []


def check(name: str, condition: bool) -> None:
    print(("  PASS  " if condition else "  FAIL  ") + name)
    if not condition:
        FAILURES.append(name)


def load_module():
    path = ROOT / "superset" / "security" / "login_encryption.py"
    spec = importlib.util.spec_from_file_location("login_encryption", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encrypt_like_browser(password: str, server_pub: str, nonce: str) -> str:
    """Python mirror of superset-frontend/src/pages/Login/passwordEncryption.ts"""
    peer = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b64u_decode(server_pub)
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


NODE_ENCRYPT = r"""
const { webcrypto } = require('node:crypto');
const subtle = webcrypto.subtle;
const toBytes = s => Uint8Array.from(
  Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64'));
const toB64u = b => Buffer.from(b).toString('base64')
  .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
(async () => {
  const [serverPub, nonce, password] = process.argv.slice(1);
  const enc = new TextEncoder();
  const curve = { name: 'ECDH', namedCurve: 'P-256' };
  const serverKey = await subtle.importKey('raw', toBytes(serverPub), curve, false, []);
  const pair = await subtle.generateKey(curve, true, ['deriveBits']);
  const shared = await subtle.deriveBits(
    { name: 'ECDH', public: serverKey }, pair.privateKey, 256);
  const salt = webcrypto.getRandomValues(new Uint8Array(16));
  const iv = webcrypto.getRandomValues(new Uint8Array(12));
  const hkdf = await subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey']);
  const aes = await subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt, info: enc.encode('superset-login-msg-v1') },
    hkdf, { name: 'AES-GCM', length: 256 }, false, ['encrypt']);
  const ct = await subtle.encrypt(
    { name: 'AES-GCM', iv }, aes, enc.encode(JSON.stringify({ p: password, n: nonce })));
  const pub = await subtle.exportKey('raw', pair.publicKey);
  console.log(['v1', toB64u(pub), toB64u(salt), toB64u(iv), toB64u(ct)].join('.'));
})().catch(e => { console.error(e); process.exit(1); });
"""


def part1_offline() -> None:
    print("\nPART 1 - login_encryption module")
    mod = load_module()
    secret = "unit-test-secret-key"
    server_pub = mod.server_public_key(secret)
    nonce = "nonce-abc123"
    password = "P@ssw0rd!'\"\\ unicode-é中"

    blob = encrypt_like_browser(password, server_pub, nonce)
    check("Python-client blob decrypts to the original password",
          mod.decrypt_login_password(secret, blob, nonce) == password)
    check("blob does not contain the plaintext password",
          password not in blob and "P@ssw0rd" not in blob)
    check("wrong nonce is rejected",
          mod.decrypt_login_password(secret, blob, "another-nonce") is None)
    check("missing nonce is rejected",
          mod.decrypt_login_password(secret, blob, None) is None)
    check("different SECRET_KEY cannot decrypt",
          mod.decrypt_login_password("other-secret", blob, nonce) is None)
    parts = blob.split(".")
    tampered = ".".join(parts[:4] + [b64u(b"x" + b64u_decode(parts[4])[1:])])
    check("tampered ciphertext is rejected",
          mod.decrypt_login_password(secret, tampered, nonce) is None)
    for garbage in ("", "v1", "v1.a.b.c.d", "v2." + ".".join(parts[1:]), "x" * 5000):
        check(f"garbage blob {garbage[:12]!r} is rejected",
              mod.decrypt_login_password(secret, garbage, nonce) is None)
    check("two encryptions of the same password differ",
          encrypt_like_browser(password, server_pub, nonce)
          != encrypt_like_browser(password, server_pub, nonce))
    check("server public key is stable for a given SECRET_KEY",
          mod.server_public_key(secret) == server_pub)

    node = shutil.which("node")
    if not node:
        print("  SKIP  Web Crypto interop (node not found on PATH)")
        return
    result = subprocess.run(
        [node, "-e", NODE_ENCRYPT, server_pub, nonce, password],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        check("Node Web Crypto ran (%s)" % result.stderr.strip()[:120], False)
        return
    web_blob = result.stdout.strip()
    check("Web Crypto (browser primitives) blob decrypts to the original password",
          mod.decrypt_login_password(secret, web_blob, nonce) == password)


class Session:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def cookie(self) -> str:
        return next((c.value for c in self.jar if c.name == "session"), "")

    def call(self, method, path, body=None, headers=None, cookie=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Accept", "application/json")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        opener = (urllib.request.build_opener() if cookie is not None
                  else self.opener)
        if cookie is not None:
            req.add_header("Cookie", "session=" + cookie)
        try:
            with opener.open(req, timeout=15) as resp:
                return resp.status, resp.read().decode(errors="replace")
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode(errors="replace")


def part2_online() -> None:
    base = os.environ.get("SUPERSET_URL")
    user = os.environ.get("SUPERSET_TEST_USER")
    password = os.environ.get("SUPERSET_TEST_PASSWORD")
    print("\nPART 2 - live server")
    if not (base and user and password):
        print("  SKIP  set SUPERSET_URL / SUPERSET_TEST_USER / "
              "SUPERSET_TEST_PASSWORD to run")
        return

    def fresh_login(s: Session):
        _, body = s.call("GET", "/api/v1/security/csrf_token/")
        csrf = json.loads(body)["result"]
        _, body = s.call("GET", "/login/captcha")
        challenge = json.loads(body)
        payload = {"username": user, "captcha_answer": challenge["code"]}
        if "key" in challenge:
            payload["enc_password"] = encrypt_like_browser(
                password, challenge["key"], challenge["nonce"])
        else:
            payload["password"] = password
        headers = {"X-CSRFToken": csrf}
        status, resp = s.call("POST", "/login/", payload, headers)
        return csrf, payload, headers, status, resp, challenge

    for legacy in ("/resetmypassword/form", "/resetpassword/form",
                   "/users/add", "/users/edit/1"):
        check(f"classic plaintext password form {legacy} is blocked (404)",
              Session(base).call("GET", legacy)[0] == 404)

    ghost = "nouser-" + os.urandom(4).hex()
    codes = [Session(base).call("POST", "/api/v1/security/login", {
        "username": ghost, "password": "wrong", "provider": "db"})[0]
        for _ in range(8)]
    check("JWT API login is throttled after repeated failures "
          f"(got {codes})", 429 in codes and codes[0] == 401)

    s = Session(base)
    csrf, payload, headers, status, resp, challenge = fresh_login(s)
    check("challenge advertises an encryption key and nonce", "key" in challenge)
    check("login request body carries enc_password, not password",
          "enc_password" in payload and "password" not in payload)
    check("plaintext password is nowhere in the request body",
          password not in json.dumps(payload))
    check("encrypted login succeeds (HTTP 200)", status == 200)
    if status != 200:
        print("        server said:", resp[:200])
        return

    old_cookie = s.cookie()
    check("authenticated with the session cookie",
          s.call("GET", "/api/v1/me/")[0] == 200)

    s.call("GET", "/logout/")
    status, _ = s.call("GET", "/api/v1/me/", cookie=old_cookie)
    check("cookie captured BEFORE logout is rejected AFTER logout "
          "(the Burp PoC)", status == 401)
    status, _ = s.call("GET", "/api/v1/me/")
    check("normal session is logged out too", status == 401)

    # Same session, logged out: the CAPTCHA answer and encryption nonce were
    # both consumed by the first login, so the identical request must fail.
    status, _ = s.call("POST", "/login/", payload, headers)
    check("replaying the exact same login request is rejected",
          status in (400, 401, 403))
    check("...and did not log the session back in",
          s.call("GET", "/api/v1/me/")[0] == 401)

    s2 = Session(base)
    csrf2, _, _, status2, _, _ = fresh_login(s2)
    check("a fresh login after all that still works", status2 == 200)
    check("and gets a different session cookie", s2.cookie() != old_cookie)
    if status2 != 200:
        return

    # ---- authenticated password change over the encrypted channel ----
    check("password_key needs authentication",
          Session(base).call("GET", "/api/v1/me/password_key")[0] == 401)
    headers2 = {"X-CSRFToken": csrf2}

    def key_and_nonce():
        _, raw = s2.call("GET", "/api/v1/me/password_key")
        return json.loads(raw)["result"]

    kn = key_and_nonce()
    check("logged-in session gets a key and a nonce",
          bool(kn.get("key") and kn.get("nonce")))
    new_password = "Zz9!" + os.urandom(6).hex()
    body = {"enc_password": encrypt_like_browser(
        new_password, kn["key"], kn["nonce"])}
    check("change-password body carries no plaintext",
          new_password not in json.dumps(body) and "password" not in body)
    status, resp = s2.call("PUT", "/api/v1/me/", body, headers2)
    check("PUT /api/v1/me/ with enc_password only succeeds (HTTP 200)",
          status == 200)
    if status != 200:
        print("        server said:", resp[:200])
    status, _ = s2.call("PUT", "/api/v1/me/", body, headers2)
    check("replaying that PUT is rejected (nonce already used)", status == 400)

    kn2 = key_and_nonce()
    good = encrypt_like_browser(new_password + "!", kn2["key"], kn2["nonce"])
    head, *rest = good.split(".")
    bad = ".".join([head] + rest[:3] + [b64u(b"x" + b64u_decode(rest[3])[1:])])
    status, _ = s2.call("PUT", "/api/v1/me/", {"enc_password": bad}, headers2)
    check("tampered encrypted password is rejected", status == 400)

    kn3 = key_and_nonce()
    wrong_nonce = encrypt_like_browser(new_password + "!", kn3["key"], "stale")
    status, _ = s2.call("PUT", "/api/v1/me/", {"enc_password": wrong_nonce},
                        headers2)
    check("encrypted password with the wrong nonce is rejected",
          status == 400)

    print("        (waiting 61s for the login rate limit to reset)")
    time.sleep(61)
    s2.call("GET", "/logout/")
    s4 = Session(base)
    password_before, password = password, new_password
    _, _, _, status4, _, _ = fresh_login(s4)
    check("the NEW password really works for login", status4 == 200)
    password = password_before
    if os.environ.get("SUPERSET_TEST_IS_ADMIN") == "1" and status4 == 200:
        part3_admin(base, s4, fresh_login)


def part3_admin(base, admin, fresh_login) -> None:
    print("\nPART 3 - admin creates/updates a user with an encrypted password")
    _, raw = admin.call("GET", "/api/v1/security/csrf_token/")
    csrf = json.loads(raw)["result"]
    headers = {"X-CSRFToken": csrf}

    def enc(pw):
        _, raw = admin.call("GET", "/api/v1/me/password_key")
        kn = json.loads(raw)["result"]
        return encrypt_like_browser(pw, kn["key"], kn["nonce"])

    _, raw = admin.call("GET", "/api/v1/security/roles/search/")
    role_ids = [r["id"] for r in json.loads(raw).get("result", [])
                if r.get("name") == "Gamma"]
    name = "zz_audit_tmp2"
    created_pw = "Aa1!" + os.urandom(6).hex()
    body = {"first_name": "Tmp", "last_name": "Two", "username": name,
            "email": name + "@example.invalid", "active": True,
            "roles": role_ids, "enc_password": enc(created_pw)}
    check("create-user body carries no plaintext",
          created_pw not in json.dumps(body) and "password" not in body)
    status, resp = admin.call("POST", "/api/v1/security/users/", body, headers)
    check("POST /api/v1/security/users/ with enc_password succeeds (201)",
          status == 201)
    if status != 201:
        print("        server said:", resp[:300])
        return
    user_id = json.loads(resp)["id"]
    try:
        print("        (waiting 61s for the login rate limit to reset)")
        time.sleep(61)
        other = Session(base)
        globals_pw = {"u": name, "p": created_pw}
        _, raw = other.call("GET", "/api/v1/security/csrf_token/")
        c2 = json.loads(raw)["result"]
        _, raw = other.call("GET", "/login/captcha")
        ch = json.loads(raw)
        status, _ = other.call("POST", "/login/", {
            "username": globals_pw["u"], "captcha_answer": ch["code"],
            "enc_password": encrypt_like_browser(
                globals_pw["p"], ch["key"], ch["nonce"])}, {"X-CSRFToken": c2})
        check("the created user can log in with the encrypted-then-stored "
              "password", status == 200)

        new_pw = "Bb2!" + os.urandom(6).hex()
        status, resp = admin.call(
            "PUT", f"/api/v1/security/users/{user_id}",
            {"enc_password": enc(new_pw)}, headers)
        check("PUT /api/v1/security/users/<id> with enc_password succeeds",
              status == 200)
        if status != 200:
            print("        server said:", resp[:300])
    finally:
        status, _ = admin.call("DELETE", f"/api/v1/security/users/{user_id}",
                               None, headers)
        check("cleanup: temporary user deleted", status == 200)


if __name__ == "__main__":
    part1_offline()
    part2_online()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} CHECK(S) FAILED:")
        for name in FAILURES:
            print("  -", name)
        sys.exit(1)
    print("All checks passed.")
