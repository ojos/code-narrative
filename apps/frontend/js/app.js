/**
 * @file アプリケーションのエントリポイント（オーケストレーション層）。
 *
 * 設定読込 → 認証（コールバック処理・状態反映）→ フォーム/履歴のイベント配線 →
 * 変換投入とポーリングまでを束ねる。個別ロジックは config / auth / api / ui / models に委譲する。
 */

import { loadConfig } from "./config.js";
import { AuthClient } from "./auth.js";
import { ApiClient, ApiError } from "./api.js";
import { ALLOWED_MODELS, PROMPT_PRESETS, isAllowedModel } from "./models.js";
import { validateRepoUrl } from "./validation.js";
import * as ui from "./ui.js";

/** 結果ポーリングの間隔（ミリ秒）。 */
const POLL_INTERVAL_MS = 3000;
/** ポーリングの最大試行回数（POLL_INTERVAL_MS × 回数 が実質のタイムアウト）。 */
const POLL_MAX_ATTEMPTS = 100;
/** 履歴一覧の取得件数。 */
const HISTORY_LIMIT = 20;

/**
 * 現在アクティブに監視しているジョブ ID。
 *
 * 履歴の連続クリックや新規投入で切り替わる。`pollUntilDone` は待機明けに本値と
 * 自分の jobId を照合し、非アクティブになったポーリングを即中断して #result-area の
 * 競合更新（画面の明滅・不要な API 継続）を防ぐ。
 *
 * @type {string|null}
 */
let activeJobId = null;

/**
 * ジョブが終端状態に達したかを判定する。
 *
 * @param {string} status - ジョブのステータス。
 * @returns {boolean} completed または failed のとき true。
 */
function isTerminalStatus(status) {
  return status === "completed" || status === "failed";
}

/**
 * 指定ミリ秒だけ待機する。
 *
 * @param {number} ms - 待機時間（ミリ秒）。
 * @returns {Promise<void>}
 */
function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * アプリ全体を初期化する。設定エラー時はバナーを表示して停止する。
 *
 * @returns {Promise<void>}
 */
async function bootstrap() {
  const banner = ui.byId("global-banner");

  let config;
  try {
    config = loadConfig();
  } catch (error) {
    console.error("設定の読み込みに失敗しました。", error);
    ui.showBanner(banner, error instanceof Error ? error.message : String(error));
    return;
  }

  const auth = new AuthClient(config);
  const api = new ApiClient(config.apiBaseUrl, () => auth.getValidAccessToken());

  try {
    await auth.handleRedirectCallback();
  } catch (error) {
    console.error("認証コールバックの処理に失敗しました。", error);
    ui.showBanner(banner, error instanceof Error ? error.message : String(error));
  }

  wireStaticUi();
  wireAuthControls(auth);
  applyAuthState(auth);

  if (auth.isAuthenticated()) {
    wireConvertForm(auth, api);
    await refreshHistory(api);
  }
}

/**
 * モデル選択・プリセットボタンなど、認証状態に依らない UI を配線する。
 *
 * @returns {void}
 */
function wireStaticUi() {
  const modelSelect = /** @type {HTMLSelectElement} */ (ui.byId("model-select"));
  ui.renderModelOptions(modelSelect, ALLOWED_MODELS);

  const promptField = /** @type {HTMLTextAreaElement} */ (ui.byId("custom-prompt"));
  ui.renderPromptPresets(ui.byId("preset-buttons"), PROMPT_PRESETS, (prompt) => {
    promptField.value = prompt;
    promptField.focus();
  });
}

/**
 * ログイン・ログアウトのボタンを配線する。
 *
 * @param {AuthClient} auth - 認証クライアント。
 * @returns {void}
 */
function wireAuthControls(auth) {
  ui.byId("login-btn").addEventListener("click", () => {
    auth.login().catch((error) => {
      console.error(error);
      ui.showBanner(ui.byId("global-banner"), "ログインを開始できませんでした。");
    });
  });
  ui.byId("logout-btn").addEventListener("click", () => auth.logout());
}

/**
 * 認証状態をヘッダーとビューに反映する。
 *
 * @param {AuthClient} auth - 認証クライアント。
 * @returns {void}
 */
function applyAuthState(auth) {
  ui.setAuthView({
    authed: auth.isAuthenticated(),
    loginView: ui.byId("view-login"),
    appView: ui.byId("view-app"),
    loginBtn: ui.byId("login-btn"),
    logoutBtn: ui.byId("logout-btn"),
  });
}

/**
 * 変換フォームの送信を配線する。
 *
 * @param {AuthClient} auth - 認証クライアント。
 * @param {ApiClient} api - API クライアント。
 * @returns {void}
 */
function wireConvertForm(auth, api) {
  const form = /** @type {HTMLFormElement} */ (ui.byId("convert-form"));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitConversion(api).catch((error) => {
      console.error("変換の投入に失敗しました。", error);
      const message = error instanceof ApiError && error.status === 401
        ? "セッションが切れています。ログインし直してください。"
        : error instanceof Error ? error.message : String(error);
      ui.setFormError(ui.byId("form-error"), message);
    });
  });
}

/**
 * フォーム入力を検証し、変換ジョブを投入してポーリングを開始する。
 *
 * @param {ApiClient} api - API クライアント。
 * @returns {Promise<void>}
 */
async function submitConversion(api) {
  const errorEl = ui.byId("form-error");
  ui.setFormError(errorEl, "");

  const repoInput = /** @type {HTMLInputElement} */ (ui.byId("repo-url"));
  const promptInput = /** @type {HTMLTextAreaElement} */ (ui.byId("custom-prompt"));
  const modelSelect = /** @type {HTMLSelectElement} */ (ui.byId("model-select"));
  const submitBtn = /** @type {HTMLButtonElement} */ (ui.byId("submit-btn"));

  const repoResult = validateRepoUrl(repoInput.value);
  if (!repoResult.valid) {
    ui.setFormError(errorEl, repoResult.error ?? "リポジトリ URL が不正です。");
    return;
  }
  if (!isAllowedModel(modelSelect.value)) {
    ui.setFormError(errorEl, "許可されていないモデルが選択されています。");
    return;
  }

  submitBtn.disabled = true;
  try {
    const accepted = await api.createNarrative({
      repo_url: repoResult.normalized,
      custom_prompt: promptInput.value,
      model_id: modelSelect.value,
    });
    await pollUntilDone(api, accepted.job_id);
    await refreshHistory(api);
  } finally {
    submitBtn.disabled = false;
  }
}

/**
 * ジョブが終端状態になるまで結果取得 API をポーリングし、都度描画する。
 *
 * @param {ApiClient} api - API クライアント。
 * @param {string} jobId - 監視対象ジョブ ID。
 * @returns {Promise<void>}
 */
async function pollUntilDone(api, jobId) {
  const resultArea = ui.byId("result-area");
  // このポーリングを唯一のアクティブ監視として登録する。以降に別ジョブが選択されると
  // activeJobId が変わり、本ループは待機明けの照合で中断される。
  activeJobId = jobId;

  for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
    let job;
    try {
      job = await api.getNarrative(jobId);
    } catch (error) {
      console.error("結果取得に失敗しました。", error);
      if (jobId !== activeJobId) {
        return;
      }
      ui.renderResult(resultArea, { job_id: jobId, status: "failed", error_message: "結果取得に失敗しました。" });
      return;
    }

    // API 応答待ちの間に別ジョブへ切り替わっていたら、描画も継続もせず中断する。
    if (jobId !== activeJobId) {
      return;
    }

    ui.renderResult(resultArea, job);
    if (isTerminalStatus(String(job.status))) {
      return;
    }
    await delay(POLL_INTERVAL_MS);

    // 待機中に別ジョブへ切り替わっていたら中断する。
    if (jobId !== activeJobId) {
      return;
    }
  }

  if (jobId !== activeJobId) {
    return;
  }
  ui.renderResult(resultArea, {
    job_id: jobId,
    status: "failed",
    error_message: "タイムアウトしました。履歴から後ほど確認してください。",
  });
}

/**
 * 履歴一覧を取得して描画する。
 *
 * @param {ApiClient} api - API クライアント。
 * @returns {Promise<void>}
 */
async function refreshHistory(api) {
  const listEl = ui.byId("history-list");
  try {
    const response = await api.listNarratives({ limit: HISTORY_LIMIT });
    const items = Array.isArray(response.items) ? response.items : [];
    ui.renderHistory(listEl, items, (job) => {
      const jobId = String(job.job_id ?? "");
      if (jobId !== "") {
        pollUntilDone(api, jobId).catch((error) => console.error(error));
      }
    });
  } catch (error) {
    console.error("履歴の取得に失敗しました。", error);
    ui.renderHistory(listEl, [], () => {});
  }
}

// DOM 構築後に起動する。
if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    bootstrap().catch((error) => console.error("初期化に失敗しました。", error));
  });
}

export { bootstrap, isTerminalStatus };
