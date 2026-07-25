/**
 * @file 実行時設定（`window.APP_CONFIG`）の読み取りと検証。
 *
 * 実値はリポジトリにハードコードせず、CI がデプロイ時に生成する `config.js` が
 * `window.APP_CONFIG` を定義する（SPEC §4⑤ / shared-ai-rules §2）。本モジュールは
 * その値を検証し、派生値（Cognito Hosted UI / authorize / token / logout の各 URL）を
 * 組み立てて返す。
 *
 * @typedef {Object} RawAppConfig
 * @property {string} apiEndpoint            - HTTP API のベース URL（terraform output api_endpoint）。
 * @property {string} region                 - AWS リージョン（例: ap-northeast-1）。
 * @property {string} cognitoUserPoolId      - Cognito User Pool ID。
 * @property {string} cognitoClientId        - Cognito App Client ID（公開クライアント）。
 * @property {string} cognitoHostedUiDomain  - Hosted UI ドメインプレフィックス（例: code-narrative-auth）。
 * @property {string} redirectUri            - コールバック URL（例: https://code-narrative.ojos.jp/callback）。
 * @property {string} logoutUri              - ログアウト後の戻り先（例: https://code-narrative.ojos.jp/）。
 *
 * @typedef {Object} AppConfig
 * @property {string} apiEndpoint
 * @property {string} region
 * @property {string} cognitoClientId
 * @property {string} redirectUri
 * @property {string} logoutUri
 * @property {string} hostedUiBaseUrl - https://<domain>.auth.<region>.amazoncognito.com
 * @property {string} authorizeUrl    - OAuth2 authorize エンドポイント。
 * @property {string} tokenUrl        - OAuth2 token エンドポイント。
 * @property {string} logoutUrl       - Hosted UI logout エンドポイント。
 * @property {string} apiBaseUrl      - `${apiEndpoint}/api/v1` を正規化した値。
 */

/**
 * 設定に必須のキー一覧。いずれかが欠けると起動時にエラーとする。
 * @type {ReadonlyArray<keyof RawAppConfig>}
 */
const REQUIRED_KEYS = Object.freeze([
  "apiEndpoint",
  "region",
  "cognitoUserPoolId",
  "cognitoClientId",
  "cognitoHostedUiDomain",
  "redirectUri",
  "logoutUri",
]);

/**
 * 末尾スラッシュを除去する。
 *
 * @param {string} value - 対象文字列。
 * @returns {string} 末尾スラッシュを取り除いた文字列。
 */
function stripTrailingSlash(value) {
  return value.replace(/\/+$/, "");
}

/**
 * `window.APP_CONFIG`（または任意のソース）を検証し、派生 URL を組み立てて返す。
 *
 * @param {RawAppConfig} [source] - 省略時は `globalThis.window.APP_CONFIG` を読む。
 * @returns {AppConfig} 検証済みの設定。
 * @throws {Error} 設定が未注入、または必須キーが欠けている場合。
 */
export function loadConfig(source) {
  const raw = source ?? globalThis.window?.APP_CONFIG;

  if (raw === undefined || raw === null || typeof raw !== "object") {
    throw new Error(
      "APP_CONFIG が読み込まれていません。config.js が生成・配信されているか確認してください。",
    );
  }

  const missing = REQUIRED_KEYS.filter((key) => {
    const value = raw[key];
    return typeof value !== "string" || value.trim() === "";
  });

  if (missing.length > 0) {
    throw new Error(`APP_CONFIG に必須項目が不足しています: ${missing.join(", ")}`);
  }

  const hostedUiBaseUrl = `https://${raw.cognitoHostedUiDomain}.auth.${raw.region}.amazoncognito.com`;
  const apiBaseUrl = `${stripTrailingSlash(raw.apiEndpoint)}/api/v1`;

  return Object.freeze({
    apiEndpoint: stripTrailingSlash(raw.apiEndpoint),
    region: raw.region,
    cognitoClientId: raw.cognitoClientId,
    redirectUri: raw.redirectUri,
    logoutUri: raw.logoutUri,
    hostedUiBaseUrl,
    authorizeUrl: `${hostedUiBaseUrl}/oauth2/authorize`,
    tokenUrl: `${hostedUiBaseUrl}/oauth2/token`,
    logoutUrl: `${hostedUiBaseUrl}/logout`,
    apiBaseUrl,
  });
}
