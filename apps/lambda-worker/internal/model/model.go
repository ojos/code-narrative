// Package model は lambda-worker 全体で共有するドメイン型を定義する。
//
// このパッケージは AWS SDK や HTTP といったインフラ層に依存しない、
// 純粋なデータ構造のみを保持する。各機能パッケージ（ghclient / extract /
// bedrock / store / worker）はここで定義した型を介して値を受け渡す。
package model

// JobMessage は SQS メッセージ本文をデコードした 1 件の変換ジョブ要求を表す。
//
// 各フィールドは REST API（apps/api）が SQS へ投入する JSON に対応する。
type JobMessage struct {
	// JobID は DynamoDB のパーティションキー（UUID v4）。
	JobID string `json:"job_id"`
	// RepoURL は変換対象の GitHub リポジトリ URL（https://github.com/{owner}/{repo}）。
	RepoURL string `json:"repo_url"`
	// CustomPrompt は世界観・スタイル指定（任意）。
	CustomPrompt string `json:"custom_prompt"`
	// ModelID は呼び出す Bedrock モデル ID（ホワイトリスト検証対象）。
	ModelID string `json:"model_id"`
}

// Commit は GitHub のコミット 1 件分の要旨を表す。
type Commit struct {
	// Message はコミットメッセージ。
	Message string
	// Date はコミット日時（ISO8601 文字列）。
	Date string
	// Author は作者名。
	Author string
}

// Usage は Bedrock 応答に含まれる入出力トークン使用量を表す。
type Usage struct {
	// InputTokens は入力トークン数。
	InputTokens int32 `json:"input_tokens"`
	// OutputTokens は生成トークン数。
	OutputTokens int32 `json:"output_tokens"`
}

// GenerationResult は Bedrock による 1 回の生成結果を表す。
type GenerationResult struct {
	// Story は生成されたショートショート本文。
	Story string
	// Usage はトークン使用量。
	Usage Usage
}

// Material は LLM へ渡す物語素材（プロンプト構成要素）を保持する。
//
// extract パッケージが構築し、bedrock パッケージが SPEC §4② の
// User Request テンプレートへ差し込む。
type Material struct {
	// DirectoryTree はディレクトリツリー（全ファイルパス一覧）。
	DirectoryTree string
	// Readme は README 本文。
	Readme string
	// SelectedFiles はヒューリスティックで選定した主要ソースファイルの内容。
	SelectedFiles string
	// CommitLog は整形済みのコミットログ。
	CommitLog string
	// CustomPrompt は世界観・スタイル指定（worker がジョブ要求から補完）。
	CustomPrompt string
}
