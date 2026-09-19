/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

/**
 * Encrypts the login password to the server's public key before it leaves
 * the page (audit findings #2 / #4), so a captured or proxied login request
 * carries ciphertext instead of the password. Must stay byte-for-byte in
 * step with superset/security/login_encryption.py:
 *
 *   ECDH P-256 (ephemeral client key) -> HKDF-SHA256 (random salt) ->
 *   AES-256-GCM over {"p": password, "n": server nonce}
 *
 * Wire format: "v1.<client_pub>.<salt>.<iv>.<ciphertext+tag>", each part
 * unpadded base64url.
 */

import { SupersetClient } from '@superset-ui/core';

const MESSAGE_KEY_INFO = 'superset-login-msg-v1';

function bytesToBase64Url(data: ArrayBuffer | Uint8Array): string {
  const view = data instanceof Uint8Array ? data : new Uint8Array(data);
  let binary = '';
  view.forEach(byte => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function base64UrlToBytes(text: string) {
  const base64 = text.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(base64 + '='.repeat((4 - (base64.length % 4)) % 4));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Web Crypto only exists in secure contexts (HTTPS or localhost). On a plain
 * HTTP host it is undefined and the caller falls back to the plain field,
 * exactly as before -- never a broken login.
 */
export function canEncryptPassword(): boolean {
  return (
    typeof window !== 'undefined' &&
    !!window.crypto &&
    !!window.crypto.subtle &&
    typeof TextEncoder !== 'undefined'
  );
}

export async function encryptPassword(
  password: string,
  serverPublicKey: string,
  nonce: string,
): Promise<string> {
  const { subtle } = window.crypto;
  const encoder = new TextEncoder();
  const curve = { name: 'ECDH', namedCurve: 'P-256' };

  const serverKey = await subtle.importKey(
    'raw',
    base64UrlToBytes(serverPublicKey),
    curve,
    false,
    [],
  );
  const clientKeys = await subtle.generateKey(curve, true, ['deriveBits']);
  const sharedSecret = await subtle.deriveBits(
    { name: 'ECDH', public: serverKey },
    clientKeys.privateKey,
    256,
  );

  const salt = window.crypto.getRandomValues(new Uint8Array(16));
  const iv = window.crypto.getRandomValues(new Uint8Array(12));
  const hkdfKey = await subtle.importKey(
    'raw',
    sharedSecret,
    'HKDF',
    false,
    ['deriveKey'],
  );
  const aesKey = await subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt,
      info: encoder.encode(MESSAGE_KEY_INFO),
    },
    hkdfKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt'],
  );
  const ciphertext = await subtle.encrypt(
    { name: 'AES-GCM', iv },
    aesKey,
    encoder.encode(JSON.stringify({ p: password, n: nonce })),
  );
  const clientPublicKey = await subtle.exportKey('raw', clientKeys.publicKey);

  return [
    'v1',
    bytesToBase64Url(clientPublicKey),
    bytesToBase64Url(salt),
    bytesToBase64Url(iv),
    bytesToBase64Url(ciphertext),
  ].join('.');
}

/**
 * For the authenticated password-entry paths (change my password, admin
 * creates/updates a user): swaps a plain `password` in the payload for an
 * encrypted `enc_password`, using a key + single-use nonce fetched just
 * before submit. Anything that stops encryption (no Web Crypto on a plain
 * HTTP host, endpoint unreachable, ...) returns the payload untouched, so
 * the save still works exactly as it did before.
 */
export async function withEncryptedPassword(
  payload: Record<string, any>,
): Promise<Record<string, any>> {
  const { password, ...rest } = payload;
  if (typeof password !== 'string' || !password || !canEncryptPassword()) {
    return payload;
  }
  try {
    const { json } = await SupersetClient.get({
      endpoint: '/api/v1/me/password_key',
    });
    const { key, nonce } = json.result || {};
    if (!key || !nonce) {
      return payload;
    }
    return { ...rest, enc_password: await encryptPassword(password, key, nonce) };
  } catch (_error) {
    return payload;
  }
}
