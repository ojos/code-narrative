/**
 * @file DOM 描画・イベント補助（ビュー層）。
 *
 * ビジネスロジック（auth / api）を持たず、要素の生成・表示切替・文言描画のみを担う。
 * 生成テキストやエラー文言は必ず textContent で挿入し、XSS を防ぐ。
 */

/**
 * ID から要素を取得する。存在しなければ例外を投げる。
 *
 * @param {string} id - 要素の id。
 * @returns {HTMLElement} 見つかった要素。
 * @throws {Error} 要素が存在しない場合。
 */
export function byId(id) {
  const element = document.getElementById(id);
  if (element === null) {
    throw new Error(`要素が見つかりません: #${id}`);
  }
  return element;
}

/**
 * 要素の表示・非表示を切り替える。
 *
 * @param {HTMLElement} element - 対象要素。
 * @param {boolean} visible - 表示するなら true。
 * @returns {void}
 */
export function setVisible(element, visible) {
  element.hidden = !visible;
}

/**
 * モデルホワイトリストを select 要素の option として描画する。
 *
 * @param {HTMLSelectElement} selectEl - 対象 select。
 * @param {ReadonlyArray<{ id: string, label: string }>} models - モデル一覧。
 * @returns {void}
 */
export function renderModelOptions(selectEl, models) {
  selectEl.replaceChildren();
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = model.label;
    selectEl.append(option);
  }
}

/**
 * プロンプトプリセットをボタン群として描画する。
 *
 * @param {HTMLElement} containerEl - ボタンを配置するコンテナ。
 * @param {ReadonlyArray<{ label: string, prompt: string }>} presets - プリセット一覧。
 * @param {(prompt: string) => void} onPick - ボタン押下時のコールバック。
 * @returns {void}
 */
export function renderPromptPresets(containerEl, presets, onPick) {
  containerEl.replaceChildren();
  for (const preset of presets) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset-btn";
    button.textContent = preset.label;
    button.addEventListener("click", () => onPick(preset.prompt));
    containerEl.append(button);
  }
}

/**
 * 認証状態に応じてヘッダーとビューの表示を切り替える。
 *
 * @param {{ authed: boolean, loginView: HTMLElement, appView: HTMLElement, loginBtn: HTMLElement, logoutBtn: HTMLElement }} params
 * @returns {void}
 */
export function setAuthView({ authed, loginView, appView, loginBtn, logoutBtn }) {
  setVisible(loginView, !authed);
  setVisible(appView, authed);
  setVisible(loginBtn, !authed);
  setVisible(logoutBtn, authed);
}

/**
 * フォームのエラー文言を表示・消去する。
 *
 * @param {HTMLElement} element - エラー表示要素。
 * @param {string} [message] - 表示するメッセージ。空なら消去。
 * @returns {void}
 */
export function setFormError(element, message = "") {
  element.textContent = message;
  setVisible(element, message !== "");
}

/**
 * 画面上部のバナー（設定エラー等の致命的通知）を表示する。
 *
 * @param {HTMLElement} element - バナー要素。
 * @param {string} message - 表示文言。
 * @returns {void}
 */
export function showBanner(element, message) {
  element.textContent = message;
  setVisible(element, true);
}

/**
 * 変換ジョブの現在状態を結果エリアへ描画する。
 *
 * @param {HTMLElement} container - 結果エリア要素。
 * @param {Record<string, any>} job - ジョブレコード（status / generated_story / error_message 等）。
 * @returns {void}
 */
export function renderResult(container, job) {
  container.replaceChildren();
  setVisible(container, true);

  const status = String(job.status ?? "unknown");
  const heading = document.createElement("h3");
  heading.textContent = `ジョブ ${job.job_id ?? ""}`;
  container.append(heading);

  const statusLine = document.createElement("p");
  statusLine.className = `status status-${status}`;
  statusLine.textContent = `状態: ${statusLabel(status)}`;
  container.append(statusLine);

  if (status === "completed") {
    const story = document.createElement("pre");
    story.className = "story";
    story.textContent = String(job.generated_story ?? "");
    container.append(story);
  } else if (status === "failed") {
    const error = document.createElement("p");
    error.className = "error-text";
    error.textContent = String(job.error_message ?? "変換に失敗しました。");
    container.append(error);
  } else {
    const pending = document.createElement("p");
    pending.className = "pending";
    pending.textContent = "生成中です。しばらくお待ちください…";
    container.append(pending);
  }
}

/**
 * 履歴一覧を描画する。
 *
 * @param {HTMLElement} container - 一覧コンテナ（ul 要素）。
 * @param {Array<Record<string, any>>} items - ジョブ一覧。
 * @param {(job: Record<string, any>) => void} onSelect - 項目選択時のコールバック。
 * @returns {void}
 */
export function renderHistory(container, items, onSelect) {
  container.replaceChildren();
  if (items.length === 0) {
    const empty = document.createElement("li");
    empty.className = "history-empty";
    empty.textContent = "まだ変換履歴はありません。";
    container.append(empty);
    return;
  }
  for (const item of items) {
    container.append(buildHistoryItem(item, onSelect));
  }
}

/**
 * 履歴の 1 項目を表す li 要素を生成する。
 *
 * @param {Record<string, any>} job - ジョブレコード。
 * @param {(job: Record<string, any>) => void} onSelect - 選択コールバック。
 * @returns {HTMLLIElement} li 要素。
 */
function buildHistoryItem(job, onSelect) {
  const li = document.createElement("li");
  li.className = "history-item";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "history-link";
  button.addEventListener("click", () => onSelect(job));

  const repo = document.createElement("span");
  repo.className = "history-repo";
  repo.textContent = String(job.repo_url ?? "(不明なリポジトリ)");

  const meta = document.createElement("span");
  meta.className = "history-meta";
  meta.textContent = `${statusLabel(String(job.status ?? "unknown"))} / ${String(job.created_at ?? "")}`;

  button.append(repo, meta);
  li.append(button);
  return li;
}

/**
 * ステータス値を日本語ラベルへ変換する。
 *
 * @param {string} status - API のステータス値。
 * @returns {string} 表示用ラベル。
 */
function statusLabel(status) {
  const labels = {
    queued: "受付済み",
    processing: "処理中",
    completed: "完了",
    failed: "失敗",
  };
  return labels[status] ?? status;
}
