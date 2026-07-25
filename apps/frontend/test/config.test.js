/**
 * @file config.js の単体テスト。必須検証と派生 URL 組み立てを確認する。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { loadConfig } from "../js/config.js";

/** テスト用の完全な設定。 */
const VALID = Object.freeze({
  apiEndpoint: "https://abc123.execute-api.ap-northeast-1.amazonaws.com/",
  region: "ap-northeast-1",
  cognitoUserPoolId: "ap-northeast-1_ABCDE",
  cognitoClientId: "client123",
  cognitoHostedUiDomain: "code-narrative-auth",
  redirectUri: "https://code-narrative.ojos.jp/callback",
  logoutUri: "https://code-narrative.ojos.jp/",
});

test("有効な設定から派生 URL を組み立てる", () => {
  const config = loadConfig(VALID);
  assert.equal(config.apiBaseUrl, "https://abc123.execute-api.ap-northeast-1.amazonaws.com/api/v1");
  assert.equal(config.hostedUiBaseUrl, "https://code-narrative-auth.auth.ap-northeast-1.amazoncognito.com");
  assert.equal(config.authorizeUrl, "https://code-narrative-auth.auth.ap-northeast-1.amazoncognito.com/oauth2/authorize");
  assert.equal(config.tokenUrl, "https://code-narrative-auth.auth.ap-northeast-1.amazoncognito.com/oauth2/token");
  assert.equal(config.logoutUrl, "https://code-narrative-auth.auth.ap-northeast-1.amazoncognito.com/logout");
});

test("設定未注入なら例外", () => {
  assert.throws(() => loadConfig(undefined), /APP_CONFIG/);
});

test("必須項目欠落なら不足キーを示して例外", () => {
  const { cognitoClientId, ...partial } = VALID;
  assert.throws(() => loadConfig(partial), /cognitoClientId/);
});

test("空文字は欠落として扱う", () => {
  assert.throws(() => loadConfig({ ...VALID, region: "  " }), /region/);
});
