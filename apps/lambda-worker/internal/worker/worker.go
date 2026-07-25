// Package worker は SQS メッセージ 1 件分の処理フローを統括する。
//
// 取得（ghclient）→ 展開・抽出（extract）→ 生成（bedrock）→ 永続化（store）を
// 束ね、冪等性・部分バッチ失敗応答・失敗記録といった信頼性設計（SPEC §4②）を
// 実装する。外部 I/O はすべてインターフェイス経由で注入し、単体テストで
// 実 AWS / ネットワークに接続せず検証できるようにする。
package worker

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"os"
	"time"

	"github.com/aws/aws-lambda-go/events"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/bedrock"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/extract"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/ghclient"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/logging"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/store"
)

// RepoFetcher は GitHub からのリポジトリ取得を抽象化する。
type RepoFetcher interface {
	// FetchTarball は tar.gz ストリームを返す。呼び出し側が Close する。
	FetchTarball(ctx context.Context, owner, repo string) (io.ReadCloser, error)
	// FetchCommits は直近 limit 件のコミットを返す。
	FetchCommits(ctx context.Context, owner, repo string, limit int) ([]model.Commit, error)
}

// Extractor は tarball 展開と物語素材抽出を抽象化する。
type Extractor interface {
	// Untar は tar.gz を destDir へ展開する。累計サイズが上限超過なら extract.ErrTooLarge。
	Untar(r io.Reader, destDir string, maxTotalBytes int64) (*extract.ExtractedRepo, error)
	// SelectMaterial は素材（第 1 返り値）と repo_digest（第 2 返り値）を返す。
	SelectMaterial(repo *extract.ExtractedRepo, commits []model.Commit, maxBytes int) (*model.Material, string, error)
}

// Generator は Bedrock による物語生成を抽象化する。
type Generator interface {
	Generate(ctx context.Context, modelID string, m model.Material) (model.GenerationResult, error)
}

// Store は DynamoDB へのジョブ状態書き込みを抽象化する。
type Store interface {
	// MarkProcessing はリース方式で processing を獲得する。cutoff はリース失効の
	// 判定境界（now - リース期間）の ISO8601 UTC 文字列。
	MarkProcessing(ctx context.Context, jobID, cutoff string) error
	MarkCompleted(ctx context.Context, jobID string, res store.CompletedResult) error
	MarkFailed(ctx context.Context, jobID, errMessage string) error
}

// Config は worker の動作パラメータ（SPEC §4② の各上限）を保持する。
type Config struct {
	// TmpDir は tarball 展開先のルート（既定 /tmp）。
	TmpDir string
	// MaxExtractBytes は展開後サイズの上限（200MB）。
	MaxExtractBytes int64
	// MaterialMaxBytes は LLM 素材の合計上限（100KB）。
	MaterialMaxBytes int
	// CommitLimit は取得するコミット件数（30）。
	CommitLimit int
	// ProcessingLease は processing リースの有効期間（既定 900 秒）。
	// この期間を過ぎても completed/failed に至らない processing ジョブは、
	// 再配信時に stale とみなされ再取得される。可視性タイムアウト相当以上を想定。
	ProcessingLease time.Duration
}

// DefaultConfig は SPEC §4② の既定値を返す。
func DefaultConfig() Config {
	return Config{
		TmpDir:           "/tmp",
		MaxExtractBytes:  200 * 1024 * 1024,
		MaterialMaxBytes: 100 * 1024,
		CommitLimit:      30,
		ProcessingLease:  900 * time.Second,
	}
}

// Worker は依存を注入されたジョブ処理器。
type Worker struct {
	store     Store
	fetcher   RepoFetcher
	extractor Extractor
	generator Generator
	cfg       Config
	// newLogger は job_id 付きロガーの生成関数（テストで差し替え可能）。
	newLogger func(jobID string) *logging.Logger
	// now は現在時刻取得関数（リース cutoff 算出用。テストで固定するため注入可能）。
	now func() time.Time
}

// New は依存と設定から Worker を生成する。
func New(st Store, fetcher RepoFetcher, extractor Extractor, gen Generator, cfg Config) *Worker {
	return &Worker{
		store:     st,
		fetcher:   fetcher,
		extractor: extractor,
		generator: gen,
		cfg:       cfg,
		newLogger: logging.New,
		now:       time.Now,
	}
}

// Handle は SQS イベントを処理し、失敗メッセージのみを ReportBatchItemFailures で返す。
//
// Process が非 nil を返したメッセージ（一時障害）のみ再配信対象とする。
// 本文が壊れているメッセージは再試行しても回復しないため、ログのみ記録して破棄する。
func (w *Worker) Handle(ctx context.Context, event events.SQSEvent) (events.SQSEventResponse, error) {
	var resp events.SQSEventResponse
	for _, record := range event.Records {
		var msg model.JobMessage
		if err := json.Unmarshal([]byte(record.Body), &msg); err != nil {
			slog.Error("SQS メッセージ本文の JSON 解析に失敗、破棄します",
				"message_id", record.MessageId, "error", err.Error())
			continue
		}
		if err := w.Process(ctx, msg); err != nil {
			resp.BatchItemFailures = append(resp.BatchItemFailures,
				events.SQSBatchItemFailure{ItemIdentifier: record.MessageId})
		}
	}
	return resp, nil
}

// Process は 1 件のジョブを処理する。
//
// 返り値が非 nil の場合のみ「再配信すべき一時障害」を意味する。業務エラー
// （不正な repo_url / model_id、サイズ超過、破損 tarball 等）は status=failed を
// 記録した上で nil を返し、再配信を避ける。冪等スキップも nil を返す。
func (w *Worker) Process(ctx context.Context, msg model.JobMessage) error {
	log := w.newLogger(msg.JobID)

	// 1. リース方式で processing を獲得（queued、または stale な processing のみ成功）。
	cutoff := w.now().UTC().Add(-w.cfg.ProcessingLease).Format(time.RFC3339)
	if err := w.store.MarkProcessing(ctx, msg.JobID, cutoff); err != nil {
		if errors.Is(err, store.ErrAlreadyProcessing) {
			log.Info("処理中（リース有効）または処理済みのためスキップ")
			return nil
		}
		log.Error("processing 遷移に失敗（再配信）", "error", err.Error())
		return err
	}

	// 2. repo_url 解析（業務エラー → failed 確定）。
	owner, repo, err := ghclient.ParseRepoURL(msg.RepoURL)
	if err != nil {
		return w.fail(ctx, log, msg.JobID, "repo_url の解析に失敗", err)
	}

	// 3. model_id ホワイトリスト検証（業務エラー → failed 確定）。
	if err := bedrock.ValidateModelID(msg.ModelID); err != nil {
		return w.fail(ctx, log, msg.JobID, "model_id が不正", err)
	}

	// 4. tarball 取得（一時障害 → 再配信）。
	tarball, err := w.fetcher.FetchTarball(ctx, owner, repo)
	if err != nil {
		log.Error("tarball 取得に失敗（再配信）", "error", err.Error())
		return err
	}
	defer tarball.Close()

	// 5. 展開先を作成（インフラ障害 → 再配信）。
	destDir, err := os.MkdirTemp(w.cfg.TmpDir, "repo-*")
	if err != nil {
		log.Error("展開先ディレクトリ作成に失敗（再配信）", "error", err.Error())
		return err
	}
	defer os.RemoveAll(destDir)

	// 6. 展開（サイズ超過・破損 → failed 確定）。
	extracted, err := w.extractor.Untar(tarball, destDir, w.cfg.MaxExtractBytes)
	if err != nil {
		if errors.Is(err, extract.ErrTooLarge) {
			return w.fail(ctx, log, msg.JobID, "リポジトリサイズが上限(200MB)を超過", err)
		}
		return w.fail(ctx, log, msg.JobID, "tarball の展開に失敗", err)
	}

	// 7. コミットログ取得（致命ではない: 失敗しても空で続行）。
	commits, err := w.fetcher.FetchCommits(ctx, owner, repo, w.cfg.CommitLimit)
	if err != nil {
		log.Warn("コミットログ取得に失敗、空で続行", "error", err.Error())
		commits = nil
	}

	// 8. 物語素材抽出（合計 100KB 上限）。
	material, digest, err := w.extractor.SelectMaterial(extracted, commits, w.cfg.MaterialMaxBytes)
	if err != nil {
		return w.fail(ctx, log, msg.JobID, "物語素材の抽出に失敗", err)
	}
	material.CustomPrompt = msg.CustomPrompt

	// 9. Bedrock 生成（API 障害 → 再配信）。
	result, err := w.generator.Generate(ctx, msg.ModelID, *material)
	if err != nil {
		log.Error("bedrock 生成に失敗（再配信）", "error", err.Error())
		return err
	}

	// 10. 完了書き込み（書き込み障害 → 再配信）。
	if err := w.store.MarkCompleted(ctx, msg.JobID, store.CompletedResult{
		Story:      result.Story,
		RepoDigest: digest,
		ModelID:    msg.ModelID,
		Usage:      result.Usage,
	}); err != nil {
		log.Error("completed 書き込みに失敗（再配信）", "error", err.Error())
		return err
	}

	log.Info("変換ジョブ完了",
		"input_tokens", result.Usage.InputTokens,
		"output_tokens", result.Usage.OutputTokens)
	return nil
}

// fail は failed 状態を記録し、原則として nil（再配信不要）を返す。
//
// ただし failed の記録自体に失敗した場合は、状態が queued/processing のまま
// 取り残されるのを避けるため err を返して再配信させる。
func (w *Worker) fail(ctx context.Context, log *logging.Logger, jobID, reason string, cause error) error {
	log.Error(reason, "error", cause.Error())
	message := reason + ": " + cause.Error()
	if err := w.store.MarkFailed(ctx, jobID, message); err != nil {
		log.Error("failed 状態の記録に失敗（再配信）", "error", err.Error())
		return err
	}
	return nil
}
