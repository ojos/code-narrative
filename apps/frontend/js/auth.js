/**
 * @file Cognito 認証クライアント（Authorization Code Grant + PKCE）。
 *
 * SPEC §4⑤ に従い、Hosted UI へのリダイレクトでログインし、コールバックで受け取った
 * 認可コードを PKCE で検証しつつトークンへ交換する。Implicit フローは使用しない。
 * トークンは sessionStorage に保持し、アクセストークン失効時はリフレッシュを試みる。
 */

import { generateCodeVerifier, generateCodeChallenge, generateState } from "./pkce.js";

/** sessionStorage 上のキー名（衝突を避けるため接頭辞を付ける）。 */
const STORAGE_KEYS = Object.freeze({
  codeVerifier: "cn.pkce.verifier",
  state: "cn.oauth.state",
  tokens: "cn.auth.tokens",
});

/** アクセストークン失効の前倒しマージン（秒）。境界での 401 を避ける。 */
const EXPIRY_SKEW_SECONDS = 30;

/**
 * Cognito Hosted UI を用いた認証フローを担うクライアント。
 */
export class AuthClient {
  /**
   * @param {import("./config.js").AppConfig} config - 検証済みアプリ設定。
   * @param {Storage} [storage] - トークン等の保存先。既定は sessionStorage。
   */
  constructor(config, storage) {
    /** @type {import("./config.js").AppConfig} */
    this.config = config;
    /** @type {Storage} */
    this.storage = storage ?? globalThis.sessionStorage;
  }

  /**
   * 保存済みトークン一式を取得する。
   *
   * @returns {{ access_token: string, id_token?: string, refresh_token?: string, expires_at: number }|null}
   *   保存が無い、または壊れている場合は null。
   */
  getStoredTokens() {
    const raw = this.storage.getItem(STORAGE_KEYS.tokens);
    if (raw === null) {
      return null;
    }
    try {
      return JSON.parse(raw);
    } catch (error) {
      console.error("保存済みトークンの解析に失敗しました。", error);
      this.storage.removeItem(STORAGE_KEYS.tokens);
      return null;
    }
  }

  /**
   * 有効なセッションを保持しているかを判定する（失効前後は問わない）。
   *
   * @returns {boolean} トークンが保存されていれば true。
   */
  isAuthenticated() {
    return this.getStoredTokens() !== null;
  }

  /**
   * PKCE パラメータを生成・保存し、Hosted UI の authorize へリダイレクトする。
   *
   * @returns {Promise<void>} リダイレクト開始まで解決しない（実際にはページ遷移する）。
   * @throws {Error} 暗号処理に失敗した場合。
   */
  async login() {
    try {
      const codeVerifier = generateCodeVerifier();
      const codeChallenge = await generateCodeChallenge(codeVerifier);
      const state = generateState();

      this.storage.setItem(STORAGE_KEYS.codeVerifier, codeVerifier);
      this.storage.setItem(STORAGE_KEYS.state, state);

      const params = new URLSearchParams({
        response_type: "code",
        client_id: this.config.cognitoClientId,
        redirect_uri: this.config.redirectUri,
        scope: "openid email profile",
        state,
        code_challenge: codeChallenge,
        code_challenge_method: "S256",
      });

      globalThis.location.assign(`${this.config.authorizeUrl}?${params.toString()}`);
    } catch (error) {
      console.error("ログイン開始に失敗しました。", error);
      throw new Error("ログインを開始できませんでした。時間をおいて再試行してください。");
    }
  }

  /**
   * コールバック URL のクエリを解析し、認可コードをトークンへ交換する。
   *
   * `?code=...&state=...` を含まない通常表示では何もせず false を返す。処理後は
   * URL からクエリを除去して履歴を汚さない。
   *
   * @returns {Promise<boolean>} コールバックを処理した場合に true。
   * @throws {Error} state 不一致やトークン交換失敗など、認証に失敗した場合。
   */
  async handleRedirectCallback() {
    const url = new URL(globalThis.location.href);
    const code = url.searchParams.get("code");
    const returnedState = url.searchParams.get("state");
    const errorParam = url.searchParams.get("error");

    if (errorParam !== null) {
      this.#clearPkceParams();
      throw new Error(`認可サーバーがエラーを返しました: ${errorParam}`);
    }

    if (code === null) {
      return false;
    }

    const expectedState = this.storage.getItem(STORAGE_KEYS.state);
    const codeVerifier = this.storage.getItem(STORAGE_KEYS.codeVerifier);

    if (expectedState === null || returnedState !== expectedState) {
      this.#clearPkceParams();
      throw new Error("state が一致しません。認証をやり直してください。");
    }
    if (codeVerifier === null) {
      this.#clearPkceParams();
      throw new Error("PKCE code_verifier が見つかりません。認証をやり直してください。");
    }

    await this.#exchangeCodeForTokens(code, codeVerifier);
    this.#clearPkceParams();
    this.#stripCallbackQuery(url);
    return true;
  }

  /**
   * API 呼び出しに用いる有効なアクセストークンを返す。
   *
   * 失効間近ならリフレッシュを試み、リフレッシュ不能ならトークンを破棄して null を返す。
   *
   * @returns {Promise<string|null>} 有効なアクセストークン。取得不能なら null。
   */
  async getValidAccessToken() {
    const tokens = this.getStoredTokens();
    if (tokens === null) {
      return null;
    }

    const nowSeconds = Math.floor(Date.now() / 1000);
    if (nowSeconds < tokens.expires_at - EXPIRY_SKEW_SECONDS) {
      return tokens.access_token;
    }

    if (typeof tokens.refresh_token === "string") {
      try {
        const refreshed = await this.#refreshTokens(tokens.refresh_token);
        return refreshed.access_token;
      } catch (error) {
        console.error("トークンのリフレッシュに失敗しました。", error);
      }
    }

    this.storage.removeItem(STORAGE_KEYS.tokens);
    return null;
  }

  /**
   * トークンを破棄し、Hosted UI のログアウトへリダイレクトする。
   *
   * @returns {void}
   */
  logout() {
    this.storage.removeItem(STORAGE_KEYS.tokens);
    this.#clearPkceParams();

    const params = new URLSearchParams({
      client_id: this.config.cognitoClientId,
      logout_uri: this.config.logoutUri,
    });
    globalThis.location.assign(`${this.config.logoutUrl}?${params.toString()}`);
  }

  /**
   * 認可コードをトークンエンドポイントで交換して保存する。
   *
   * @param {string} code - 認可コード。
   * @param {string} codeVerifier - PKCE code_verifier。
   * @returns {Promise<void>}
   * @throws {Error} HTTP エラーやレスポンス不正時。
   * @private
   */
  async #exchangeCodeForTokens(code, codeVerifier) {
    const body = new URLSearchParams({
      grant_type: "authorization_code",
      client_id: this.config.cognitoClientId,
      code,
      redirect_uri: this.config.redirectUri,
      code_verifier: codeVerifier,
    });
    const response = await this.#postToken(body);
    this.#persistTokenResponse(response);
  }

  /**
   * リフレッシュトークンでアクセストークンを更新して保存する。
   *
   * リフレッシュ応答には refresh_token が含まれないため、既存の値を引き継ぐ。
   *
   * @param {string} refreshToken - 保存済みリフレッシュトークン。
   * @returns {Promise<{ access_token: string, expires_at: number }>} 更新後の値。
   * @throws {Error} HTTP エラー時。
   * @private
   */
  async #refreshTokens(refreshToken) {
    const body = new URLSearchParams({
      grant_type: "refresh_token",
      client_id: this.config.cognitoClientId,
      refresh_token: refreshToken,
    });
    const response = await this.#postToken(body);
    return this.#persistTokenResponse({ refresh_token: refreshToken, ...response });
  }

  /**
   * トークンエンドポイントへ POST する共通処理。
   *
   * @param {URLSearchParams} body - application/x-www-form-urlencoded ボディ。
   * @returns {Promise<Record<string, unknown>>} JSON パース済みレスポンス。
   * @throws {Error} HTTP ステータスが 2xx でない場合。
   * @private
   */
  async #postToken(body) {
    const response = await fetch(this.config.tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`トークンエンドポイントがエラーを返しました (${response.status}): ${detail}`);
    }
    return response.json();
  }

  /**
   * トークンレスポンスに失効時刻を付与して sessionStorage に保存する。
   *
   * @param {Record<string, any>} response - トークンエンドポイントのレスポンス。
   * @returns {{ access_token: string, id_token?: string, refresh_token?: string, expires_at: number }}
   * @private
   */
  #persistTokenResponse(response) {
    const expiresIn = typeof response.expires_in === "number" ? response.expires_in : 3600;
    const tokens = {
      access_token: response.access_token,
      id_token: response.id_token,
      refresh_token: response.refresh_token,
      expires_at: Math.floor(Date.now() / 1000) + expiresIn,
    };
    this.storage.setItem(STORAGE_KEYS.tokens, JSON.stringify(tokens));
    return tokens;
  }

  /**
   * PKCE の一時パラメータ（verifier / state）を破棄する。
   *
   * @returns {void}
   * @private
   */
  #clearPkceParams() {
    this.storage.removeItem(STORAGE_KEYS.codeVerifier);
    this.storage.removeItem(STORAGE_KEYS.state);
  }

  /**
   * コールバック処理後に URL からクエリ文字列を除去する。
   *
   * @param {URL} url - 現在の URL。
   * @returns {void}
   * @private
   */
  #stripCallbackQuery(url) {
    if (typeof globalThis.history?.replaceState === "function") {
      globalThis.history.replaceState({}, document.title, url.pathname);
    }
  }
}
