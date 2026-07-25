/**
 * config.example.js — 実行時設定のプレースホルダ。
 *
 * このファイルは「キー名だけを持つ雛形」です（shared-ai-rules §2）。実値はコミットせず、
 * CI がデプロイ時に同じ構造の `config.js` を生成して S3 へ配置します（terraform outputs から注入）。
 * ローカルで構造確認したい場合は、本ファイルを `config.js` にコピーして各値を埋めてください。
 *
 * 対応する terraform output（feat/t3-iac）:
 *   apiEndpoint           <- api_endpoint
 *   region                <- ap-northeast-1（固定）
 *   cognitoUserPoolId     <- cognito_user_pool_id
 *   cognitoClientId       <- cognito_client_id
 *   cognitoHostedUiDomain <- cognito_hosted_ui_domain（ドメインプレフィックスのみ）
 *   redirectUri           <- https://code-narrative.ojos.jp/callback
 *   logoutUri             <- https://code-narrative.ojos.jp/
 */
window.APP_CONFIG = {
  apiEndpoint: "https://REPLACE_ME.execute-api.ap-northeast-1.amazonaws.com",
  region: "ap-northeast-1",
  cognitoUserPoolId: "ap-northeast-1_REPLACEME",
  cognitoClientId: "REPLACE_ME_CLIENT_ID",
  cognitoHostedUiDomain: "code-narrative-auth",
  redirectUri: "https://code-narrative.ojos.jp/callback",
  logoutUri: "https://code-narrative.ojos.jp/",
};
