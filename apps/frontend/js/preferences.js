/**
 * @file 変換フォーム入力のブラウザ永続化。
 *
 * リポジトリ URL / カスタムプロンプト / モデル選択を localStorage に保持し、
 * リロードや Hosted UI からのリダイレクト復帰でも同じ入力状態を復元する。
 * ログアウト時は `clear()` で破棄し、共用ブラウザで前の利用者の入力が残らないようにする。
 *
 * 認証トークンの保存先（sessionStorage / `cn.auth.*`）とはキー空間を分けており、
 * 本モジュールは `cn.form.*` のみを扱う。
 */

import { ALLOWED_MODELS, isAllowedModel } from "./models.js";

/** localStorage 上のキー名（衝突を避けるため auth.js と同じ `cn.` 接頭辞を付ける）。 */
export const STORAGE_KEY = "cn.form.draft";

/**
 * custom_prompt を保存する際の上限文字数。
 *
 * API 側の上限（SPEC §4① / `apps/api` の 2000 文字）と同値に保つ。上限を超える値が
 * 保存されていても、復元した瞬間にフォームが 422 確定の状態になるのを避ける。
 */
export const PROMPT_MAX_LENGTH = 2000;

/**
 * フォーム入力の下書き。
 *
 * @typedef {object} FormDraft
 * @property {string} repoUrl - GitHub リポジトリ URL。
 * @property {string} customPrompt - カスタムプロンプト。
 * @property {string} modelId - 選択中のモデル ID。
 */

/**
 * 復元対象が無い、または保存値が信頼できないときに返す初期状態。
 *
 * @returns {FormDraft} 初期状態の下書き。
 */
function initialDraft() {
  return {
    repoUrl: "",
    customPrompt: "",
    modelId: ALLOWED_MODELS[0].id,
  };
}

/**
 * 使用する Storage を解決する。
 *
 * Safari のプライベートモード等では `globalThis.localStorage` の参照自体が例外に
 * なる。ここで吸収して null を返し、保存・復元だけを静かに無効化する（フォーム本体の
 * 初期化は止めない）。
 *
 * @param {Storage} [storage] - 明示的に使う Storage。省略時は localStorage。
 * @returns {Storage|null} 利用可能な Storage。利用できない場合は null。
 */
function resolveStorage(storage) {
  if (storage !== undefined) {
    return storage;
  }
  try {
    return globalThis.localStorage ?? null;
  } catch (error) {
    console.warn("localStorage を利用できないため、入力の保存を無効化します。", error);
    return null;
  }
}

/**
 * 保存値を検証して下書きへ正規化する。
 *
 * ホワイトリストの正本は models.js であり、保存後にホワイトリストが変わりうる
 * （実績: モデル 2 件 → 5 件への拡張）。そのため検証は書き込み時ではなく本関数、
 * すなわち読み書きの両方が通る位置で行う。
 *
 * @param {unknown} value - 検証対象（JSON.parse の結果、またはフォームからの値）。
 * @returns {FormDraft} 正規化済みの下書き。
 */
function normalizeDraft(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return initialDraft();
  }
  const source = /** @type {Record<string, unknown>} */ (value);
  return {
    repoUrl: typeof source.repoUrl === "string" ? source.repoUrl : "",
    customPrompt:
      typeof source.customPrompt === "string" ? source.customPrompt.slice(0, PROMPT_MAX_LENGTH) : "",
    modelId: isAllowedModel(String(source.modelId)) ? String(source.modelId) : ALLOWED_MODELS[0].id,
  };
}

/**
 * 保存済みの下書きを読み出す。
 *
 * 保存が無い・壊れている・値が信頼できない場合はいずれも初期状態を返し、呼び出し側に
 * 分岐を持たせない。壊れた値はキーごと削除して次回以降の無駄な解析を避ける。
 *
 * @param {Storage} [storage] - 読み出し元。省略時は localStorage。
 * @returns {FormDraft} 復元した下書き。
 */
export function load(storage) {
  const store = resolveStorage(storage);
  if (store === null) {
    return initialDraft();
  }

  let raw;
  try {
    raw = store.getItem(STORAGE_KEY);
  } catch (error) {
    console.warn("保存済み入力の読み出しに失敗しました。", error);
    return initialDraft();
  }
  if (raw === null) {
    return initialDraft();
  }

  try {
    return normalizeDraft(JSON.parse(raw));
  } catch (error) {
    console.error("保存済み入力の解析に失敗しました。", error);
    remove(store);
    return initialDraft();
  }
}

/**
 * 下書きを保存する。
 *
 * @param {Partial<FormDraft>} draft - 保存する入力値。
 * @param {Storage} [storage] - 保存先。省略時は localStorage。
 * @returns {boolean} 保存できた場合に true。
 */
export function save(draft, storage) {
  const store = resolveStorage(storage);
  if (store === null) {
    return false;
  }
  try {
    store.setItem(STORAGE_KEY, JSON.stringify(normalizeDraft(draft)));
    return true;
  } catch (error) {
    // 容量超過やプライベートモードでの書き込み拒否。入力操作を妨げないため通知しない。
    console.warn("入力の保存に失敗しました。", error);
    return false;
  }
}

/**
 * 保存済みの下書きを破棄する。ログアウト時に呼ぶ。
 *
 * @param {Storage} [storage] - 破棄対象。省略時は localStorage。
 * @returns {void}
 */
export function clear(storage) {
  const store = resolveStorage(storage);
  if (store !== null) {
    remove(store);
  }
}

/**
 * キーを削除する。削除自体が失敗しても呼び出し側へ例外を伝播しない。
 *
 * @param {Storage} store - 対象 Storage。
 * @returns {void}
 */
function remove(store) {
  try {
    store.removeItem(STORAGE_KEY);
  } catch (error) {
    console.warn("保存済み入力の破棄に失敗しました。", error);
  }
}
