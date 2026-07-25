/**
 * @file auth.js の単体テスト。セキュリティの要である state(CSRF) 検証・
 * code→token 交換・コールバック URL のストリップを、fake な Storage / fetch /
 * location / history を注入して検証する。
 *
 * ブラウザ専用グローバル（location / history / document / fetch）は Node には
 * 存在しないため、各テストで globalThis に fake を割り当てる。node --test は
 * ファイル単位で別プロセス実行するため、他テストへは波及しない。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { AuthClient } from "../js/auth.js";

/** sessionStorage 互換の最小 fake。内部 Map を map プロパティで公開する。 */
class FakeStorage {
  constructor() {
    /** @type {Map<string, string>} */
    this.map = new Map();
  }
  getItem(key) {
    return this.map.has(key) ? this.map.get(key) : null;
  }
  setItem(key, value) {
    this.map.set(key, String(value));
  }
  removeItem(key) {
    this.map.delete(key);
  }
}

/** テスト用の AppConfig（派生 URL は固定値）。 */
const CONFIG = Object.freeze({
  cognitoClientId: "client123",
  redirectUri: "https://code-narrative.ojos.jp/callback",
  logoutUri: "https://code-narrative.ojos.jp/",
  authorizeUrl: "https://auth.example.com/oauth2/authorize",
  tokenUrl: "https://auth.example.com/oauth2/token",
  logoutUrl: "https://auth.example.com/logout",
});

/**
 * ブラウザ環境の fake を globalThis へ設置する。
 *
 * @returns {{ location: any, history: any }} 検証で参照する fake 群。
 */
function installEnv() {
  const location = {
    href: "https://code-narrative.ojos.jp/",
    assigned: null,
    assign(url) {
      this.assigned = url;
      this.href = url;
    },
  };
  const history = {
    /** @type {string[]} replaceState に渡されたパスの記録。 */
    calls: [],
    replaceState(_state, _title, path) {
      this.calls.push(path);
    },
  };
  globalThis.location = location;
  globalThis.history = history;
  globalThis.document = { title: "code-narrative" };
  return { location, history };
}

/**
 * login() を実行し、authorize URL に載った state を取り出す。
 * これにより内部ストレージのキー名に依存せず、正しい state を echo できる。
 *
 * @param {AuthClient} auth - 対象クライアント。
 * @param {any} location - installEnv() の location fake。
 * @returns {Promise<string>} 生成された state。
 */
async function loginAndGetState(auth, location) {
  await auth.login();
  const assigned = new URL(location.assigned);
  const state = assigned.searchParams.get("state");
  assert.ok(state, "login は state を authorize URL に付与するはず");
  return state;
}

test("正常な code→token 交換でトークンを永続化し URL から code/state を除去する", async () => {
  const { location, history } = installEnv();
  const storage = new FakeStorage();
  const auth = new AuthClient(CONFIG, storage);
  const state = await loginAndGetState(auth, location);

  let captured = null;
  globalThis.fetch = async (url, init) => {
    captured = { url, init };
    return {
      ok: true,
      status: 200,
      json: async () => ({ access_token: "AT", id_token: "IT", refresh_token: "RT", expires_in: 3600 }),
    };
  };

  location.href = `${CONFIG.redirectUri}?code=abc123&state=${state}`;
  const handled = await auth.handleRedirectCallback();

  assert.equal(handled, true);
  const tokens = auth.getStoredTokens();
  assert.equal(tokens.access_token, "AT");
  assert.equal(tokens.refresh_token, "RT");
  // トークンエンドポイントへ PKCE code_verifier を添えて交換している
  assert.equal(captured.url, CONFIG.tokenUrl);
  assert.match(captured.init.body, /grant_type=authorization_code/);
  assert.match(captured.init.body, /code_verifier=/);
  // URL ストリップ: クエリ無しのパスで replaceState 済み
  assert.deepEqual(history.calls, ["/callback"]);
});

test("state 不一致は CSRF として拒否し、失敗時も URL を除去する", async () => {
  const { location, history } = installEnv();
  const auth = new AuthClient(CONFIG, new FakeStorage());
  const state = await loginAndGetState(auth, location);
  globalThis.fetch = async () => {
    throw new Error("token 交換まで到達してはならない");
  };

  location.href = `${CONFIG.redirectUri}?code=abc&state=${state}TAMPERED`;
  await assert.rejects(() => auth.handleRedirectCallback(), /state/);
  assert.deepEqual(history.calls, ["/callback"]);
});

test("保存済み state が無ければ拒否する", async () => {
  const { location } = installEnv();
  // login を経ずに state 未保存のままコールバックを処理する
  const auth = new AuthClient(CONFIG, new FakeStorage());
  location.href = `${CONFIG.redirectUri}?code=abc&state=whatever`;
  await assert.rejects(() => auth.handleRedirectCallback(), /state/);
});

test("code_verifier が無ければ拒否する", async () => {
  const { location } = installEnv();
  const storage = new FakeStorage();
  const auth = new AuthClient(CONFIG, storage);
  const state = await loginAndGetState(auth, location);
  // verifier エントリ（値が state と異なる方）だけを削除して欠落を再現する
  for (const [key, value] of storage.map) {
    if (value !== state) {
      storage.map.delete(key);
    }
  }
  location.href = `${CONFIG.redirectUri}?code=abc&state=${state}`;
  await assert.rejects(() => auth.handleRedirectCallback(), /code_verifier/);
});

test("code もエラーも無い通常表示では false を返し URL を触らない", async () => {
  const { location, history } = installEnv();
  const auth = new AuthClient(CONFIG, new FakeStorage());
  location.href = "https://code-narrative.ojos.jp/";
  const handled = await auth.handleRedirectCallback();
  assert.equal(handled, false);
  assert.deepEqual(history.calls, []);
});
