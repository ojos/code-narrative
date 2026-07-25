/**
 * @file モデルホワイトリストとプロンプトプリセットの定義。
 *
 * SPEC §4⑤ の許可モデル 3 件を単一の正本として保持する。ブラウザ API に依存しない
 * 純粋なデータ・関数のみを置き、UI とサーバー双方の期待値が食い違わないようにする。
 */

/**
 * Bedrock 呼び出しを許可するモデルのホワイトリスト。
 *
 * `id` は API へ送る `model_id`、`label` はドロップダウン表示名。
 * デプロイ先 ap-northeast-1（東京）で提供されるモデルに限定する。Claude は
 * 東京では `jp.` 地域推論プロファイル ID が必須（SPEC §4⑤）。
 *
 * @type {ReadonlyArray<{ id: string, label: string }>}
 */
export const ALLOWED_MODELS = Object.freeze([
  Object.freeze({
    id: "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
    label: "Claude Sonnet 4.5",
  }),
  Object.freeze({
    id: "amazon.nova-lite-v1:0",
    label: "Amazon Nova Lite",
  }),
]);

/**
 * カスタムプロンプト入力欄に流し込むプリセット文言。
 *
 * @type {ReadonlyArray<{ label: string, prompt: string }>}
 */
export const PROMPT_PRESETS = Object.freeze([
  Object.freeze({ label: "サイバーパンク風", prompt: "サイバーパンク風のハードボイルドな文体で書いてください。" }),
  Object.freeze({ label: "太宰治風", prompt: "太宰治のような、自嘲と哀愁の混じった一人称の文体で書いてください。" }),
  Object.freeze({ label: "SF 叙事詩風", prompt: "壮大な SF 叙事詩のような荘厳な文体で書いてください。" }),
  Object.freeze({ label: "童話風", prompt: "子ども向けの優しい童話のような文体で書いてください。" }),
]);

/**
 * 与えられたモデル ID がホワイトリストに含まれるかを判定する。
 *
 * サーバー側でも 400 で弾かれるが、送信前にクライアントでも検証して無駄な往復を防ぐ。
 *
 * @param {string} modelId - 検証対象のモデル ID。
 * @returns {boolean} ホワイトリストに含まれる場合に true。
 */
export function isAllowedModel(modelId) {
  return ALLOWED_MODELS.some((model) => model.id === modelId);
}
