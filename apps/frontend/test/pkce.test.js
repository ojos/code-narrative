/**
 * @file pkce.js の単体テスト。base64url 変換と S256 チャレンジ導出を検証する。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  base64UrlEncode,
  generateCodeVerifier,
  generateCodeChallenge,
  generateState,
} from "../js/pkce.js";

test("base64UrlEncode は URL 安全な文字のみを返す", () => {
  const encoded = base64UrlEncode(new Uint8Array([251, 255, 191, 0, 1, 2]));
  assert.match(encoded, /^[A-Za-z0-9_-]+$/);
});

test("code_verifier は毎回異なり十分な長さを持つ", () => {
  const a = generateCodeVerifier();
  const b = generateCodeVerifier();
  assert.notEqual(a, b);
  assert.ok(a.length >= 43 && a.length <= 128);
});

test("code_challenge は verifier の SHA-256 (S256, base64url) と一致する", async () => {
  const verifier = "test-code-verifier-fixed-value";
  const challenge = await generateCodeChallenge(verifier);
  const expected = createHash("sha256")
    .update(verifier)
    .digest("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  assert.equal(challenge, expected);
});

test("state は毎回異なる", () => {
  assert.notEqual(generateState(), generateState());
});
