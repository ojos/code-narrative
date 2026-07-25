/**
 * @file 入力値バリデーション（ブラウザ非依存の純粋関数）。
 *
 * SPEC §4① のサーバー側バリデーションと同じ規則をクライアントでも先行適用し、
 * 明らかに不正な入力の送信を防ぐ。最終判断はサーバーが行う。
 */

/**
 * GitHub public リポジトリ URL として許可される形式かを検証する。
 *
 * 許可形式は `https://github.com/{owner}/{repo}`（SPEC §4①）。末尾スラッシュや
 * `.git` サフィックスは許容し、正規化した URL を返す。
 *
 * @param {string} repoUrl - 検証対象の URL 文字列。
 * @returns {{ valid: boolean, normalized?: string, error?: string }}
 *   valid が true のとき normalized に正規化済み URL を格納する。
 */
export function validateRepoUrl(repoUrl) {
  if (typeof repoUrl !== "string" || repoUrl.trim() === "") {
    return { valid: false, error: "リポジトリ URL を入力してください。" };
  }

  const trimmed = repoUrl.trim();
  // owner / repo に使える文字は GitHub の規則に沿って英数・ハイフン・アンダースコア・ドット。
  const pattern = /^https:\/\/github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?\/?$/;
  const match = trimmed.match(pattern);

  if (match === null) {
    return {
      valid: false,
      error: "https://github.com/{owner}/{repo} 形式の public リポジトリ URL を入力してください。",
    };
  }

  const [, owner, repo] = match;
  return { valid: true, normalized: `https://github.com/${owner}/${repo}` };
}
