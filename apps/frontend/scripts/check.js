/**
 * @file 軽量な静的検証スクリプト（lint 相当）。
 *
 * 依存パッケージを増やさず、リポジトリ内のすべての JS に対して `node --check`
 * （構文検証）を実行する。1 件でも失敗すれば非ゼロで終了し、CI の受け入れ判定に使える。
 */

import { execFileSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));

/** 走査から除外するディレクトリ名。 */
const IGNORED_DIRS = new Set(["node_modules", "dist", ".git"]);

/**
 * 指定ディレクトリ以下の .js ファイルを再帰的に列挙する。
 *
 * @param {string} dir - 走査開始ディレクトリの絶対パス。
 * @returns {string[]} .js ファイルの絶対パス一覧。
 */
function collectJsFiles(dir) {
  /** @type {string[]} */
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!IGNORED_DIRS.has(entry.name)) {
        files.push(...collectJsFiles(join(dir, entry.name)));
      }
    } else if (extname(entry.name) === ".js") {
      files.push(join(dir, entry.name));
    }
  }
  return files;
}

/**
 * すべての JS を構文検証する。失敗があれば非ゼロ終了する。
 *
 * @returns {void}
 */
function main() {
  const files = collectJsFiles(projectRoot);
  let failed = 0;

  for (const file of files) {
    try {
      execFileSync(process.execPath, ["--check", file], { stdio: "pipe" });
    } catch (error) {
      failed += 1;
      console.error(`NG: ${file}`);
      console.error(error.stderr?.toString() ?? error.message);
    }
  }

  console.log(`checked ${files.length} JS files, ${failed} failed.`);
  if (failed > 0) {
    process.exit(1);
  }
}

main();
