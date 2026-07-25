/**
 * @file 静的サイトのビルドスクリプト（依存ゼロ）。
 *
 * 配信対象の静的アセットを `dist/` へコピーする。T5 の CI はこの `dist/` を
 * `aws s3 sync` の対象とする。バンドルは行わず、ES モジュールをそのまま配置する。
 *
 * config.js の扱い:
 *   実値の config.js は CI がデプロイ時に生成する（リポジトリには置かない）。
 *   ビルド時に本物の config.js が無ければ、ローカル構造確認用に config.example.js を
 *   dist/config.js としてコピーする（CI 環境では本物を後段で上書き配置する想定）。
 */

import { cpSync, existsSync, mkdirSync, rmSync, copyFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const distDir = join(projectRoot, "dist");

/**
 * 配信対象アセット。`from` は projectRoot 相対、`type` は file / dir。
 * @type {ReadonlyArray<{ from: string, type: "file" | "dir" }>}
 */
const ASSETS = Object.freeze([
  { from: "index.html", type: "file" },
  { from: "styles.css", type: "file" },
  { from: "js", type: "dir" },
]);

/**
 * dist をクリーンして再生成する。
 *
 * @returns {void}
 */
function resetDist() {
  rmSync(distDir, { recursive: true, force: true });
  mkdirSync(distDir, { recursive: true });
}

/**
 * 定義済みアセットを dist へコピーする。
 *
 * @returns {void}
 */
function copyAssets() {
  for (const asset of ASSETS) {
    const src = join(projectRoot, asset.from);
    const dest = join(distDir, asset.from);
    if (!existsSync(src)) {
      throw new Error(`ビルド対象が見つかりません: ${asset.from}`);
    }
    if (asset.type === "dir") {
      cpSync(src, dest, { recursive: true });
    } else {
      copyFileSync(src, dest);
    }
  }
}

/**
 * config.js を配置する。本物が無ければ example をフォールバックとして使う。
 *
 * @returns {void}
 */
function placeConfig() {
  const realConfig = join(projectRoot, "config.js");
  const exampleConfig = join(projectRoot, "config.example.js");
  const dest = join(distDir, "config.js");

  if (existsSync(realConfig)) {
    copyFileSync(realConfig, dest);
    console.log("config.js: 実ファイルを配置しました。");
  } else if (existsSync(exampleConfig)) {
    copyFileSync(exampleConfig, dest);
    console.log("config.js: プレースホルダ(config.example.js)を配置しました（CI が本番値で上書きする想定）。");
  } else {
    throw new Error("config.js も config.example.js も見つかりません。");
  }
}

/**
 * ビルドを実行する。
 *
 * @returns {void}
 */
function main() {
  resetDist();
  copyAssets();
  placeConfig();
  console.log(`ビルド完了: ${distDir}`);
}

main();
