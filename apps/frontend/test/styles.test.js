/**
 * @file styles.css の回帰テスト。
 *
 * ui.setAuthView は hidden 属性で表示を切り替えるが、作者スタイルの display 宣言は
 * ブラウザ既定の [hidden] { display: none } に優先する。styles.css から [hidden] の
 * 規則が失われると、display を持つ要素（.btn 等）で hidden が無効化され、
 * ログイン/ログアウトが両方表示される不具合が再発する（#58）。
 *
 * DOM の属性はロジック側のテストで担保されているため、ここでは CSS 側の前提が
 * 消えていないことだけを見る。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const cssPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "styles.css");
const css = fs.readFileSync(cssPath, "utf8");

/** コメントを除いた CSS 本文（コメント内の記述を規則と誤認しないため）。 */
const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, "");

/**
 * セレクタ一覧に `[hidden]` 単体を含む規則の宣言ブロックを返す。
 *
 * 単純な部分一致では `.btn[hidden] { ... }` のような個別セレクタも拾ってしまい、
 * 「display を持つ要素が増えるたびに再発する」という本来防ぎたい状態をテストが
 * 通してしまう。一方で `[hidden], .foo { ... }` のようなセレクタ併記は正しい
 * 書き方なので落としてはいけない。そのためセレクタ一覧を分解して厳密に照合する。
 *
 * @returns {string|null} 宣言ブロックの中身。該当規則が無ければ null。
 */
function hiddenRuleBody() {
  for (const [, selectors, body] of withoutComments.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    const list = selectors.split(",").map((s) => s.trim());
    if (list.includes("[hidden]")) return body;
  }
  return null;
}

test("[hidden] を非表示にする規則が存在する", () => {
  const body = hiddenRuleBody();
  assert.ok(body, "styles.css にセレクタ [hidden] の規則がない");
  assert.match(body, /display\s*:\s*none/, "[hidden] が display: none を指定していない");
});

test("[hidden] の display: none は !important で作者スタイルに優先する", () => {
  const body = hiddenRuleBody();
  assert.ok(body, "styles.css にセレクタ [hidden] の規則がない");
  assert.match(
    body,
    /display\s*:\s*none\s*!important/,
    "display を指定する要素に hidden を立てても隠れないため !important が必要",
  );
});

test("display を指定する規則が存在する（テストの前提が失われていないことの確認）", () => {
  // display 宣言が一つも無くなれば [hidden] の !important は不要になる。
  // その場合はこのテスト自体を見直す必要があるため、前提を明示的に固定する。
  assert.match(withoutComments, /\.btn\s*\{[^}]*display\s*:/);
});
