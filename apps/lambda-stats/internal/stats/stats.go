// Package stats は集計バッチのフェーズ処理を担う（SPEC §4④）。
//
// Step Functions の Scan / Aggregate / Write の各 Task が同一 Lambda を
// phase 指定で呼び出すため、フェーズ振り分けと集計ロジックをここに集約する。
// AWS SDK への依存は Scanner / Writer インターフェイス越しに閉じ込め、
// 集計ロジックを実 AWS なしで検証できるようにする。
package stats

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
)

// フェーズ名（terraform/modules/analytics/stepfunctions.tf の Payload と対応）。
const (
	PhaseScan      = "scan"
	PhaseAggregate = "aggregate"
	PhaseWrite     = "write"
)

// PromptTrendLimit は人気プロンプトとして残す上位件数。
//
// 集計結果は 1 レコードとして DynamoDB へ書くため、件数を絞って肥大化を防ぐ。
const PromptTrendLimit = 10

// ErrUnknownPhase は未知の phase を受け取った場合に返る。
var ErrUnknownPhase = errors.New("未知の phase です")

// ErrInvalidPayload は phase は既知だが必要なパラメータが欠けている場合に返る。
//
// ErrUnknownPhase と区別する。両者を混ぜると、Step Functions のペイロード組み立て
// ミスを「phase 名が誤っている」と誤って切り分けてしまう。
var ErrInvalidPayload = errors.New("phase に必要なパラメータが不足しています")

// Job は集計対象となる変換ジョブの必要最小限の射影（SPEC §4③）。
//
// Step Functions のペイロード上限（256KB）を避けるため、Scan では集計に使う
// 属性のみを取得する。
type Job struct {
	Status       string `json:"status"`
	ModelID      string `json:"model_id"`
	CustomPrompt string `json:"custom_prompt"`
	InputTokens  int64  `json:"input_tokens"`
	OutputTokens int64  `json:"output_tokens"`
}

// 以下 3 つの構造体は Step Functions のペイロード(JSON)と DynamoDB の集計レコード
// の双方になるため、json / dynamodbav の両方のタグを持たせる。
//
// attributevalue.Marshal は json タグへフォールバックせず、dynamodbav が無いと
// フィールド名そのまま(PascalCase)で書き込む。テーブル内の他属性は snake_case
// のため、タグを落とすと集計レコードだけキー命名が食い違う。

// ModelUsage はモデル別の利用件数と割合。
type ModelUsage struct {
	ModelID string  `json:"model_id" dynamodbav:"model_id"`
	Count   int64   `json:"count" dynamodbav:"count"`
	Ratio   float64 `json:"ratio" dynamodbav:"ratio"`
}

// PromptTrend はカスタムプロンプトの出現件数。
type PromptTrend struct {
	Prompt string `json:"prompt" dynamodbav:"prompt"`
	Count  int64  `json:"count" dynamodbav:"count"`
}

// TokenUsage はトークン使用量の合計。
type TokenUsage struct {
	InputTokens  int64 `json:"input_tokens" dynamodbav:"input_tokens"`
	OutputTokens int64 `json:"output_tokens" dynamodbav:"output_tokens"`
	TotalTokens  int64 `json:"total_tokens" dynamodbav:"total_tokens"`
}

// Metrics は集計結果一式（SPEC §4④ の 3 指標）。
type Metrics struct {
	// TotalJobs は集計対象となったジョブ件数（ModelUsage の Ratio の母数）。
	TotalJobs    int64         `json:"total_jobs"`
	ModelUsage   []ModelUsage  `json:"model_usage"`
	PromptTrends []PromptTrend `json:"prompt_trends"`
	TokenUsage   TokenUsage    `json:"token_usage"`
}

// Event は Step Functions から渡される入力。
//
// phase により有効なフィールドが変わる（scan は無し / aggregate は Scan /
// write は Metrics）。
type Event struct {
	Phase   string   `json:"phase"`
	Scan    []Job    `json:"scan"`
	Metrics *Metrics `json:"metrics"`
}

// WriteResult は write フェーズの結果（書き込んだレコードのキー一覧）。
type WriteResult struct {
	Date    string   `json:"date"`
	Written []string `json:"written"`
}

// Scanner は集計対象ジョブの取得を担う。
type Scanner interface {
	ScanJobs(ctx context.Context) ([]Job, error)
}

// Writer は集計結果レコードの書き込みを担う。
type Writer interface {
	// PutMetric は job_id = "STATS#<date>#<metric>" のレコードを書き込む。
	PutMetric(ctx context.Context, jobID string, payload any) error
}

// Clock は集計日の決定に用いる時刻源。テストで固定するため差し替え可能にする。
type Clock func() string

// Handler はフェーズ振り分けを行う。
type Handler struct {
	scanner Scanner
	writer  Writer
	now     Clock
}

// New は Handler を生成する。
func New(scanner Scanner, writer Writer, now Clock) *Handler {
	return &Handler{scanner: scanner, writer: writer, now: now}
}

// Handle は phase に応じた処理を実行する。
//
// 戻り値はそのまま Step Functions の Payload となるため、フェーズごとに型が
// 異なる（scan: []Job / aggregate: Metrics / write: WriteResult）。
func (h *Handler) Handle(ctx context.Context, ev Event) (any, error) {
	switch ev.Phase {
	case PhaseScan:
		jobs, err := h.scanner.ScanJobs(ctx)
		if err != nil {
			return nil, fmt.Errorf("集計対象の取得に失敗: %w", err)
		}
		return jobs, nil

	case PhaseAggregate:
		// scan 欠落を 0 件集計として通すと、Step Functions のペイロード組み立てミスに
		// 気づかないまま「全指標ゼロ」の集計結果を書き込んでしまう。
		// ジョブ 0 件の正常系は空配列 [] として渡るため nil とは区別できる
		// （Scanner は 0 件でも非 nil の空スライスを返す）。
		if ev.Scan == nil {
			return nil, fmt.Errorf("%w: phase=%s に scan がありません", ErrInvalidPayload, PhaseAggregate)
		}
		return Aggregate(ev.Scan), nil

	case PhaseWrite:
		if ev.Metrics == nil {
			return nil, fmt.Errorf("%w: phase=%s に metrics がありません", ErrInvalidPayload, PhaseWrite)
		}
		return h.write(ctx, *ev.Metrics)

	default:
		return nil, fmt.Errorf("%w: %q", ErrUnknownPhase, ev.Phase)
	}
}

// write は集計結果を指標ごとのレコードとして書き込む（SPEC §4③）。
func (h *Handler) write(ctx context.Context, m Metrics) (WriteResult, error) {
	date := h.now()
	res := WriteResult{Date: date}

	metrics := []struct {
		name    string
		payload any
	}{
		{"model_usage", map[string]any{"total_jobs": m.TotalJobs, "items": m.ModelUsage}},
		{"prompt_trends", map[string]any{"items": m.PromptTrends}},
		{"token_usage", m.TokenUsage},
	}

	for _, metric := range metrics {
		jobID := fmt.Sprintf("STATS#%s#%s", date, metric.name)
		if err := h.writer.PutMetric(ctx, jobID, metric.payload); err != nil {
			return WriteResult{}, fmt.Errorf("%s の書き込みに失敗: %w", jobID, err)
		}
		res.Written = append(res.Written, jobID)
	}
	return res, nil
}

// Aggregate はジョブ一覧から SPEC §4④ の 3 指標を算出する。
//
// 決定的な出力にするため、モデル別利用は件数降順（同数はモデル ID 昇順）、
// 人気プロンプトは件数降順（同数はプロンプト昇順）で整列する。
func Aggregate(jobs []Job) Metrics {
	modelCount := map[string]int64{}
	promptCount := map[string]int64{}
	var tokens TokenUsage
	var total int64

	for _, j := range jobs {
		total++
		if j.ModelID != "" {
			modelCount[j.ModelID]++
		}
		// 空のカスタムプロンプトは「傾向」として意味を持たないため数えない。
		if p := strings.TrimSpace(j.CustomPrompt); p != "" {
			promptCount[p]++
		}
		tokens.InputTokens += j.InputTokens
		tokens.OutputTokens += j.OutputTokens
	}
	tokens.TotalTokens = tokens.InputTokens + tokens.OutputTokens

	m := Metrics{
		TotalJobs:    total,
		ModelUsage:   modelUsage(modelCount, total),
		PromptTrends: promptTrends(promptCount),
		TokenUsage:   tokens,
	}
	return m
}

// modelUsage はモデル別の件数と割合を件数降順で返す。
func modelUsage(counts map[string]int64, total int64) []ModelUsage {
	out := make([]ModelUsage, 0, len(counts))
	for id, c := range counts {
		var ratio float64
		if total > 0 {
			ratio = float64(c) / float64(total)
		}
		out = append(out, ModelUsage{ModelID: id, Count: c, Ratio: ratio})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Count != out[j].Count {
			return out[i].Count > out[j].Count
		}
		return out[i].ModelID < out[j].ModelID
	})
	return out
}

// promptTrends は出現頻度上位 PromptTrendLimit 件を件数降順で返す。
func promptTrends(counts map[string]int64) []PromptTrend {
	out := make([]PromptTrend, 0, len(counts))
	for p, c := range counts {
		out = append(out, PromptTrend{Prompt: p, Count: c})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Count != out[j].Count {
			return out[i].Count > out[j].Count
		}
		return out[i].Prompt < out[j].Prompt
	})
	if len(out) > PromptTrendLimit {
		out = out[:PromptTrendLimit]
	}
	return out
}
