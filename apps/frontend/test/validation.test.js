/**
 * @file validation.js の単体テスト。GitHub URL 検証の受理・拒否・正規化を確認する。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { validateRepoUrl } from "../js/validation.js";

test("標準的な GitHub URL を受理する", () => {
  const result = validateRepoUrl("https://github.com/owner/repo");
  assert.ok(result.valid);
  assert.equal(result.normalized, "https://github.com/owner/repo");
});

test(".git サフィックスと末尾スラッシュを正規化する", () => {
  assert.equal(validateRepoUrl("https://github.com/owner/repo.git").normalized, "https://github.com/owner/repo");
  assert.equal(validateRepoUrl("https://github.com/owner/repo/").normalized, "https://github.com/owner/repo");
});

test("http や他ホストを拒否する", () => {
  assert.equal(validateRepoUrl("http://github.com/owner/repo").valid, false);
  assert.equal(validateRepoUrl("https://gitlab.com/owner/repo").valid, false);
});

test("owner/repo が欠けた URL を拒否する", () => {
  assert.equal(validateRepoUrl("https://github.com/owner").valid, false);
  assert.equal(validateRepoUrl("https://github.com/").valid, false);
});

test("空文字・非文字列を拒否する", () => {
  assert.equal(validateRepoUrl("").valid, false);
  assert.equal(validateRepoUrl(undefined).valid, false);
});
