/**
 * @file models.js の単体テスト。ホワイトリストが SPEC の 5 件で構成されることを保証する。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { ALLOWED_MODELS, PROMPT_PRESETS, isAllowedModel } from "../js/models.js";

test("ホワイトリストは東京提供の SPEC 5 モデル", () => {
  assert.equal(ALLOWED_MODELS.length, 5);
  const ids = ALLOWED_MODELS.map((m) => m.id);
  assert.deepEqual(ids, [
    "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "amazon.nova-lite-v1:0",
    "deepseek.v3.2",
    "qwen.qwen3-32b-v1:0",
    "google.gemma-3-12b-it",
  ]);
});

test("ベンダーが重複していない", () => {
  // 作風の振れ幅を確保するための制約（SPEC §4⑤）。id の先頭要素をベンダーとみなす
  // （地理プレフィックス付きは 2 要素目がベンダー）。
  const vendors = ALLOWED_MODELS.map((m) => {
    const parts = m.id.split(".");
    return /^(us|eu|apac|jp)$/.test(parts[0]) ? parts[1] : parts[0];
  });
  assert.equal(new Set(vendors).size, vendors.length, `ベンダー重複: ${vendors}`);
});

test("東京で無効な旧 ID(us. / Llama)は拒否する", () => {
  assert.equal(isAllowedModel("us.anthropic.claude-sonnet-4-5-20250929-v1:0"), false);
  assert.equal(isAllowedModel("us.meta.llama3-3-70b-instruct-v1:0"), false);
});

test("isAllowedModel は許可 ID を受理する", () => {
  assert.ok(isAllowedModel("amazon.nova-lite-v1:0"));
});

test("isAllowedModel は未知の ID を拒否する", () => {
  assert.equal(isAllowedModel("anthropic.claude-instant-v1"), false);
  assert.equal(isAllowedModel(""), false);
});

test("プリセットは prompt を持つ", () => {
  assert.ok(PROMPT_PRESETS.length > 0);
  for (const preset of PROMPT_PRESETS) {
    assert.equal(typeof preset.label, "string");
    assert.ok(preset.prompt.length > 0);
  }
});
