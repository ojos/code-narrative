/**
 * @file REST API クライアント（SPEC §4①）。
 *
 * `/api/v1/narratives` 系エンドポイントを Bearer JWT 付きで呼び出す。トークンの取得は
 * 呼び出し元から渡されるプロバイダ関数に委譲し、認証の詳細（AuthClient）には依存しない。
 */

/**
 * API 呼び出しが 2xx 以外を返したときに投げるエラー。
 */
export class ApiError extends Error {
  /**
   * @param {string} message - 表示用メッセージ。
   * @param {number} status - HTTP ステータスコード。
   * @param {unknown} [body] - パース済みレスポンスボディ（あれば）。
   */
  constructor(message, status, body) {
    super(message);
    this.name = "ApiError";
    /** @type {number} */
    this.status = status;
    /** @type {unknown} */
    this.body = body;
  }
}

/**
 * narratives API を呼び出すクライアント。
 */
export class ApiClient {
  /**
   * @param {string} baseUrl - `${apiEndpoint}/api/v1`。
   * @param {() => Promise<string|null>} tokenProvider - 有効なアクセストークンを返す関数。
   */
  constructor(baseUrl, tokenProvider) {
    /** @type {string} */
    this.baseUrl = baseUrl;
    /** @type {() => Promise<string|null>} */
    this.tokenProvider = tokenProvider;
  }

  /**
   * 変換ジョブを投入する（POST /api/v1/narratives）。
   *
   * @param {{ repo_url: string, custom_prompt: string, model_id: string }} payload - 投入内容。
   * @returns {Promise<{ job_id: string, status: string }>} 202 応答のボディ。
   * @throws {ApiError} 認証欠如や非 2xx 応答時。
   */
  async createNarrative(payload) {
    return this.#request("POST", "/narratives", { body: payload });
  }

  /**
   * ジョブの状態・結果を取得する（GET /api/v1/narratives/{job_id}）。
   *
   * @param {string} jobId - 対象ジョブ ID。
   * @returns {Promise<Record<string, unknown>>} ジョブレコード。
   * @throws {ApiError} 認証欠如や非 2xx 応答時。
   */
  async getNarrative(jobId) {
    return this.#request("GET", `/narratives/${encodeURIComponent(jobId)}`);
  }

  /**
   * 自分のジョブ一覧を取得する（GET /api/v1/narratives）。
   *
   * @param {{ limit?: number, nextToken?: string }} [options] - ページネーション指定。
   * @returns {Promise<{ items: Array<Record<string, unknown>>, next_token?: string }>} 一覧応答。
   * @throws {ApiError} 認証欠如や非 2xx 応答時。
   */
  async listNarratives(options = {}) {
    const query = new URLSearchParams();
    if (typeof options.limit === "number") {
      query.set("limit", String(options.limit));
    }
    if (typeof options.nextToken === "string" && options.nextToken !== "") {
      query.set("next_token", options.nextToken);
    }
    const suffix = query.toString() === "" ? "" : `?${query.toString()}`;
    return this.#request("GET", `/narratives${suffix}`);
  }

  /**
   * 認証ヘッダ付与・エラーハンドリングを共通化した fetch ラッパー。
   *
   * @param {string} method - HTTP メソッド。
   * @param {string} path - baseUrl からの相対パス（先頭スラッシュ込み）。
   * @param {{ body?: unknown }} [options] - JSON ボディ等。
   * @returns {Promise<any>} JSON パース済みレスポンス（204 は null）。
   * @throws {ApiError} 認証欠如や非 2xx 応答時。
   * @private
   */
  async #request(method, path, options = {}) {
    const token = await this.tokenProvider();
    if (token === null) {
      throw new ApiError("認証が必要です。ログインし直してください。", 401);
    }

    const headers = { Authorization: `Bearer ${token}` };
    /** @type {RequestInit} */
    const init = { method, headers };

    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }

    let response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, init);
    } catch (error) {
      throw new ApiError(`API へ接続できませんでした: ${error.message}`, 0);
    }

    const text = await response.text();
    const parsed = text === "" ? null : this.#tryParseJson(text);

    if (!response.ok) {
      const message = this.#extractErrorMessage(parsed, response.status);
      throw new ApiError(message, response.status, parsed);
    }
    return parsed;
  }

  /**
   * 例外を投げずに JSON をパースする。
   *
   * @param {string} text - レスポンス本文。
   * @returns {unknown} パース結果。失敗時は生文字列。
   * @private
   */
  #tryParseJson(text) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  /**
   * エラーレスポンスから表示用メッセージを組み立てる。
   *
   * @param {unknown} parsed - パース済みボディ。
   * @param {number} status - HTTP ステータス。
   * @returns {string} 表示用メッセージ。
   * @private
   */
  #extractErrorMessage(parsed, status) {
    if (parsed !== null && typeof parsed === "object") {
      const record = /** @type {Record<string, unknown>} */ (parsed);
      const detail = record.detail ?? record.message ?? record.error;
      if (typeof detail === "string") {
        return detail;
      }
    }
    return `API がエラーを返しました (HTTP ${status})。`;
  }
}
