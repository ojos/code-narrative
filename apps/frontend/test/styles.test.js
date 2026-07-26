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

test("[hidden] を非表示にする規則が存在する", () => {
  const rule = withoutComments.match(/\[hidden\][^{]*\{([^}]*)\}/);
  assert.ok(rule, "styles.css に [hidden] の規則がない");
  assert.match(rule[1], /display\s*:\s*none/, "[hidden] が display: none を指定していない");
});

test("[hidden] の display: none は !important で作者スタイルに優先する", () => {
  const rule = withoutComments.match(/\[hidden\][^{]*\{([^}]*)\}/);
  assert.match(
    rule[1],
    /display\s*:\s*none\s*!important/,
    "display を指定する要素に hidden を立てても隠れないため !important が必要",
  );
});

test("display を指定する規則が存在する（テストの前提が失われていないことの確認）", () => {
  // display 宣言が一つも無くなれば [hidden] の !important は不要になる。
  // その場合はこのテスト自体を見直す必要があるため、前提を明示的に固定する。
  assert.match(withoutComments, /\.btn\s*\{[^}]*display\s*:/);
});
