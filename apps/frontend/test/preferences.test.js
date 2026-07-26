/**
 * @file preferences.js の単体テスト。
 *
 * 復元は「保存後にホワイトリストや上限が変わっても壊れない」ことが要点なので、
 * 往復の一致だけでなく、信頼できない保存値を初期状態へ落とす経路を重点的に検証する。
 * localStorage は Node に存在しないため、auth.test.js と同型の fake を注入する。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { load, save, clear, STORAGE_KEY, PROMPT_MAX_LENGTH } from "../js/preferences.js";
import { ALLOWED_MODELS } from "../js/models.js";

/** localStorage 互換の最小 fake。内部 Map を map プロパティで公開する。 */
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

/** すべての操作が例外を投げる Storage（プライベートモード / 容量超過の再現）。 */
class ThrowingStorage {
  getItem() {
    throw new DOMException("SecurityError");
  }
  setItem() {
    throw new DOMException("QuotaExceededError");
  }
  removeItem() {
    throw new DOMException("SecurityError");
  }
}

/** 期待どおりに出る警告でテスト出力が汚れないよう、console を一時的に黙らせる。 */
function silenceConsole(fn) {
  const { warn, error } = console;
  console.warn = () => {};
  console.error = () => {};
  try {
    return fn();
  } finally {
    console.warn = warn;
    console.error = error;
  }
}

const DEFAULT_MODEL_ID = ALLOWED_MODELS[0].id;

test("保存した 3 値がそのまま復元される", () => {
  const storage = new FakeStorage();
  const draft = {
    repoUrl: "https://github.com/ojos/code-narrative",
    customPrompt: "太宰治風で書いてください。",
    modelId: "amazon.nova-lite-v1:0",
  };

  assert.equal(save(draft, storage), true);
  assert.deepEqual(load(storage), draft);
});

test("ホワイトリスト外のモデル ID は既定モデルへフォールバックする", () => {
  const storage = new FakeStorage();
  // 保存後にホワイトリストが変わる状況（実績: 2 件 → 5 件へ拡張）を、旧 ID の直書きで再現する。
  storage.setItem(
    STORAGE_KEY,
    JSON.stringify({ repoUrl: "", customPrompt: "", modelId: "us.meta.llama3-3-70b-instruct-v1:0" }),
  );

  assert.equal(load(storage).modelId, DEFAULT_MODEL_ID);
});

test("上限を超えるカスタムプロンプトは上限まで切り詰められる", () => {
  const storage = new FakeStorage();
  save({ repoUrl: "", customPrompt: "あ".repeat(PROMPT_MAX_LENGTH + 100), modelId: DEFAULT_MODEL_ID }, storage);

  const restored = load(storage);
  assert.equal(restored.customPrompt.length, PROMPT_MAX_LENGTH);
  // 上限ちょうどは切り詰めないこと（境界で 1 文字失わない）。
  save({ repoUrl: "", customPrompt: "い".repeat(PROMPT_MAX_LENGTH), modelId: DEFAULT_MODEL_ID }, storage);
  assert.equal(load(storage).customPrompt.length, PROMPT_MAX_LENGTH);
});

test("壊れた保存値はキーごと破棄して初期状態を返す", () => {
  const storage = new FakeStorage();
  storage.setItem(STORAGE_KEY, "{ this is not json");

  const restored = silenceConsole(() => load(storage));
  assert.deepEqual(restored, { repoUrl: "", customPrompt: "", modelId: DEFAULT_MODEL_ID });
  // 次回以降の無駄な解析を避けるため、壊れた値は残さない。
  assert.equal(storage.getItem(STORAGE_KEY), null);
});

test("JSON だがオブジェクトでない保存値も初期状態へ落とす", () => {
  const storage = new FakeStorage();
  storage.setItem(STORAGE_KEY, JSON.stringify(["https://github.com/ojos/code-narrative"]));

  assert.deepEqual(load(storage), { repoUrl: "", customPrompt: "", modelId: DEFAULT_MODEL_ID });
});

test("保存が無いときは初期状態を返す", () => {
  assert.deepEqual(load(new FakeStorage()), {
    repoUrl: "",
    customPrompt: "",
    modelId: DEFAULT_MODEL_ID,
  });
});

test("Storage が例外を投げても呼び出し側へ伝播しない", () => {
  const storage = new ThrowingStorage();

  silenceConsole(() => {
    // 保存・破棄は失敗しても例外を出さず、フォーム操作を妨げない。
    assert.equal(save({ repoUrl: "x", customPrompt: "", modelId: DEFAULT_MODEL_ID }, storage), false);
    assert.doesNotThrow(() => clear(storage));
    assert.deepEqual(load(storage), { repoUrl: "", customPrompt: "", modelId: DEFAULT_MODEL_ID });
  });
});

test("clear 後の読み出しは初期状態を返す", () => {
  const storage = new FakeStorage();
  save({ repoUrl: "https://github.com/ojos/code-narrative", customPrompt: "SF 風", modelId: DEFAULT_MODEL_ID }, storage);

  clear(storage);

  assert.equal(storage.getItem(STORAGE_KEY), null);
  assert.deepEqual(load(storage), { repoUrl: "", customPrompt: "", modelId: DEFAULT_MODEL_ID });
});
