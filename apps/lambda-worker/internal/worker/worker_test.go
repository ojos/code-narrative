package worker

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"

	"github.com/aws/aws-lambda-go/events"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/extract"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/store"
)

// --- モック群 ---

type mockStore struct {
	processingErr error
	completedErr  error
	failedErr     error

	completed *store.CompletedResult
	failedMsg string
	failedCnt int
}

func (m *mockStore) MarkProcessing(context.Context, string, string) error { return m.processingErr }
func (m *mockStore) MarkCompleted(_ context.Context, _ string, res store.CompletedResult) error {
	m.completed = &res
	return m.completedErr
}
func (m *mockStore) MarkFailed(_ context.Context, _ string, msg string) error {
	m.failedCnt++
	m.failedMsg = msg
	return m.failedErr
}

type mockFetcher struct {
	tarballErr  error
	commits     []model.Commit
	commitsErr  error
	tarballBody string
}

func (m *mockFetcher) FetchTarball(context.Context, string, string) (io.ReadCloser, error) {
	if m.tarballErr != nil {
		return nil, m.tarballErr
	}
	return io.NopCloser(strings.NewReader(m.tarballBody)), nil
}
func (m *mockFetcher) FetchCommits(context.Context, string, string, int) ([]model.Commit, error) {
	return m.commits, m.commitsErr
}

type mockExtractor struct {
	untarErr    error
	selectErr   error
	digest      string
	generateNil bool
}

func (m *mockExtractor) Untar(io.Reader, string, int64) (*extract.ExtractedRepo, error) {
	if m.untarErr != nil {
		return nil, m.untarErr
	}
	return &extract.ExtractedRepo{RootDir: "/tmp/x"}, nil
}
func (m *mockExtractor) SelectMaterial(*extract.ExtractedRepo, []model.Commit, int) (*model.Material, string, error) {
	if m.selectErr != nil {
		return nil, "", m.selectErr
	}
	return &model.Material{DirectoryTree: "main.go"}, m.digest, nil
}

type mockGenerator struct {
	result model.GenerationResult
	err    error
	called bool
}

func (m *mockGenerator) Generate(context.Context, string, model.Material) (model.GenerationResult, error) {
	m.called = true
	return m.result, m.err
}

// flakyGenerator は最初の failFirst 回だけ一時障害を返し、以降は成功する。
type flakyGenerator struct {
	failFirst int
	calls     int
	result    model.GenerationResult
}

func (g *flakyGenerator) Generate(context.Context, string, model.Material) (model.GenerationResult, error) {
	g.calls++
	if g.calls <= g.failFirst {
		return model.GenerationResult{}, errors.New("throttled")
	}
	return g.result, nil
}

// newWorker は全モックを結線した Worker を返す。
func newWorker(st Store, f RepoFetcher, e Extractor, g Generator) *Worker {
	return New(st, f, e, g, DefaultConfig())
}

const validModel = "amazon.nova-lite-v1:0"
const validRepo = "https://github.com/ojos/code-narrative"

func validMsg() model.JobMessage {
	return model.JobMessage{JobID: "job-1", RepoURL: validRepo, ModelID: validModel, CustomPrompt: "SF風"}
}

// --- テスト ---

func TestProcess_HappyPath(t *testing.T) {
	st := &mockStore{}
	gen := &mockGenerator{result: model.GenerationResult{
		Story: "物語", Usage: model.Usage{InputTokens: 10, OutputTokens: 20},
	}}
	w := newWorker(st, &mockFetcher{}, &mockExtractor{digest: "tree-digest"}, gen)

	if err := w.Process(context.Background(), validMsg()); err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}
	if st.completed == nil {
		t.Fatal("MarkCompleted が呼ばれていない")
	}
	if st.completed.Story != "物語" || st.completed.RepoDigest != "tree-digest" {
		t.Errorf("completed = %+v", st.completed)
	}
	if st.completed.Usage.InputTokens != 10 {
		t.Errorf("usage = %+v", st.completed.Usage)
	}
}

func TestProcess_IdempotentSkip(t *testing.T) {
	st := &mockStore{processingErr: store.ErrAlreadyProcessing}
	gen := &mockGenerator{}
	w := newWorker(st, &mockFetcher{}, &mockExtractor{}, gen)

	if err := w.Process(context.Background(), validMsg()); err != nil {
		t.Fatalf("冪等スキップは nil を返すべき: %v", err)
	}
	if gen.called {
		t.Error("既処理ジョブで生成が呼ばれてはならない")
	}
	if st.completed != nil || st.failedCnt != 0 {
		t.Error("既処理ジョブで completed/failed を書いてはならない")
	}
}

func TestProcess_OversizeMarksFailed(t *testing.T) {
	st := &mockStore{}
	gen := &mockGenerator{}
	w := newWorker(st, &mockFetcher{}, &mockExtractor{untarErr: extract.ErrTooLarge}, gen)

	err := w.Process(context.Background(), validMsg())
	if err != nil {
		t.Fatalf("failed 確定は nil を返すべき: %v", err)
	}
	if st.failedCnt != 1 {
		t.Fatal("MarkFailed が呼ばれていない")
	}
	if !strings.Contains(st.failedMsg, "200MB") {
		t.Errorf("error_message = %q", st.failedMsg)
	}
	if gen.called {
		t.Error("サイズ超過で生成が呼ばれてはならない")
	}
}

func TestProcess_InvalidModelMarksFailed(t *testing.T) {
	st := &mockStore{}
	msg := validMsg()
	msg.ModelID = "evil.model:1"
	w := newWorker(st, &mockFetcher{}, &mockExtractor{}, &mockGenerator{})

	err := w.Process(context.Background(), msg)
	if err != nil {
		t.Fatalf("failed 確定は nil を返すべき: %v", err)
	}
	if st.failedCnt != 1 {
		t.Fatal("MarkFailed が呼ばれていない")
	}
	if !strings.Contains(st.failedMsg, "model_id") {
		t.Errorf("error_message = %q", st.failedMsg)
	}
}

func TestProcess_InvalidRepoURLMarksFailed(t *testing.T) {
	st := &mockStore{}
	msg := validMsg()
	msg.RepoURL = "https://gitlab.com/x/y"
	w := newWorker(st, &mockFetcher{}, &mockExtractor{}, &mockGenerator{})

	if err := w.Process(context.Background(), msg); err != nil {
		t.Fatalf("failed 確定は nil を返すべき: %v", err)
	}
	if st.failedCnt != 1 || !strings.Contains(st.failedMsg, "repo_url") {
		t.Errorf("error_message = %q (cnt=%d)", st.failedMsg, st.failedCnt)
	}
}

func TestProcess_TransientFetchErrorRetries(t *testing.T) {
	st := &mockStore{}
	w := newWorker(st, &mockFetcher{tarballErr: errors.New("network down")}, &mockExtractor{}, &mockGenerator{})

	err := w.Process(context.Background(), validMsg())
	if err == nil {
		t.Fatal("一時障害は再配信のため非 nil を返すべき")
	}
	if st.failedCnt != 0 {
		t.Error("一時障害では failed を記録しない")
	}
}

func TestProcess_BedrockErrorRetries(t *testing.T) {
	st := &mockStore{}
	gen := &mockGenerator{err: errors.New("throttled")}
	w := newWorker(st, &mockFetcher{}, &mockExtractor{}, gen)

	err := w.Process(context.Background(), validMsg())
	if err == nil {
		t.Fatal("Bedrock 障害は再配信のため非 nil を返すべき")
	}
	if st.failedCnt != 0 {
		t.Error("Bedrock 一時障害では failed を記録しない")
	}
}

// TestProcess_TransientThenRedeliverCompletes は今回のリース修正の盲点を検証する。
//
// 1 回目: MarkProcessing 獲得 → Bedrock 一時障害で非 nil（再配信）。2 回目（再配信）:
// リース失効により MarkProcessing を再獲得（mock は nil を返す）→ 生成成功 →
// completed へ遷移。processing のまま取り残されず、結果喪失も起きないことを示す。
func TestProcess_TransientThenRedeliverCompletes(t *testing.T) {
	st := &mockStore{}
	gen := &flakyGenerator{failFirst: 1, result: model.GenerationResult{
		Story: "物語", Usage: model.Usage{InputTokens: 5, OutputTokens: 6},
	}}
	w := newWorker(st, &mockFetcher{}, &mockExtractor{digest: "d"}, gen)

	// 1 回目: 一時障害で再配信対象。
	if err := w.Process(context.Background(), validMsg()); err == nil {
		t.Fatal("1 回目は Bedrock 一時障害で非 nil を返すべき")
	}
	if st.completed != nil {
		t.Fatal("1 回目で completed になってはならない")
	}

	// 2 回目（再配信）: リース失効で再獲得し完了。
	if err := w.Process(context.Background(), validMsg()); err != nil {
		t.Fatalf("2 回目は完了すべき: %v", err)
	}
	if st.completed == nil {
		t.Fatal("2 回目で completed へ遷移すべき")
	}
	if st.failedCnt != 0 {
		t.Error("一時障害の再試行成功では failed を記録しない")
	}
}

func TestHandle_ReportsOnlyFailures(t *testing.T) {
	// 1 件目: 正常 / 2 件目: tarball 取得エラー（再配信対象）。
	st := &mockStore{}
	fetcher := &failSecondFetcher{}
	w := newWorker(st, fetcher, &mockExtractor{}, &mockGenerator{})

	body := `{"job_id":"j","repo_url":"` + validRepo + `","model_id":"` + validModel + `"}`
	event := events.SQSEvent{Records: []events.SQSMessage{
		{MessageId: "ok-1", Body: body},
		{MessageId: "fail-2", Body: body},
	}}

	resp, err := w.Handle(context.Background(), event)
	if err != nil {
		t.Fatalf("Handle: %v", err)
	}
	if len(resp.BatchItemFailures) != 1 {
		t.Fatalf("BatchItemFailures 件数 = %d", len(resp.BatchItemFailures))
	}
	if resp.BatchItemFailures[0].ItemIdentifier != "fail-2" {
		t.Errorf("失敗 ID = %q", resp.BatchItemFailures[0].ItemIdentifier)
	}
}

func TestHandle_MalformedBodyDropped(t *testing.T) {
	st := &mockStore{}
	w := newWorker(st, &mockFetcher{}, &mockExtractor{}, &mockGenerator{})

	event := events.SQSEvent{Records: []events.SQSMessage{
		{MessageId: "bad", Body: "{not json"},
	}}
	resp, err := w.Handle(context.Background(), event)
	if err != nil {
		t.Fatalf("Handle: %v", err)
	}
	if len(resp.BatchItemFailures) != 0 {
		t.Errorf("壊れた本文は破棄され再配信対象にしない: %+v", resp.BatchItemFailures)
	}
}

// failSecondFetcher は 2 回目の FetchTarball 呼び出しで失敗する。
type failSecondFetcher struct{ calls int }

func (f *failSecondFetcher) FetchTarball(context.Context, string, string) (io.ReadCloser, error) {
	f.calls++
	if f.calls >= 2 {
		return nil, errors.New("network down")
	}
	return io.NopCloser(strings.NewReader("")), nil
}
func (f *failSecondFetcher) FetchCommits(context.Context, string, string, int) ([]model.Commit, error) {
	return nil, nil
}
