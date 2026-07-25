/**
 * @file PKCE (RFC 7636) と OAuth ステート生成のユーティリティ。
 *
 * Web Crypto API（`globalThis.crypto`）のみを使い、ブラウザと Node の双方で動作する。
 * Authorization Code Grant + PKCE（SPEC §4⑤）に必要な code_verifier / code_challenge /
 * state を生成する。
 */

/**
 * バイト列を base64url（パディングなし）へエンコードする。
 *
 * @param {ArrayBuffer|Uint8Array} buffer - 変換対象のバイト列。
 * @returns {string} base64url 文字列。
 */
export function base64UrlEncode(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * 暗号論的乱数から base64url のランダム文字列を生成する。
 *
 * @param {number} [byteLength=32] - 乱数のバイト長。
 * @returns {string} base64url エンコードされたランダム文字列。
 */
export function randomUrlSafeString(byteLength = 32) {
  const randomBytes = new Uint8Array(byteLength);
  globalThis.crypto.getRandomValues(randomBytes);
  return base64UrlEncode(randomBytes);
}

/**
 * PKCE の code_verifier を生成する。
 *
 * RFC 7636 が定める 43〜128 文字の範囲に収まる長さの高エントロピー文字列を返す。
 *
 * @returns {string} code_verifier。
 */
export function generateCodeVerifier() {
  return randomUrlSafeString(32);
}

/**
 * code_verifier から S256 方式の code_challenge を導出する。
 *
 * @param {string} verifier - generateCodeVerifier() が返した値。
 * @returns {Promise<string>} SHA-256 ハッシュを base64url エンコードした code_challenge。
 */
export async function generateCodeChallenge(verifier) {
  const data = new TextEncoder().encode(verifier);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", data);
  return base64UrlEncode(digest);
}

/**
 * CSRF 対策用の OAuth state 値を生成する。
 *
 * @returns {string} ランダムな state 文字列。
 */
export function generateState() {
  return randomUrlSafeString(16);
}
