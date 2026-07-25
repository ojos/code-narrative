package stats

import (
	"context"
	"errors"
	"testing"
)

// fakeScanner は Scanner のテスト代替。
type fakeScanner struct {
	jobs []Job
	err  error
}

func (f *fakeScanner) ScanJobs(context.Context) ([]Job, error) { return f.jobs, f.err }

// fakeWriter は Writer のテスト代替。書き込まれたキーと本体を記録する。
type fakeWriter struct {
	keys     []string
	payloads map[string]any
	err      error
}

func (f *fakeWriter) PutMetric(_ context.Context, jobID string, payload any) error {
	if f.err != nil {
		return f.err
	}
	if f.payloads == nil {
		f.payloads = map[string]any{}
	}
	f.keys = append(f.keys, jobID)
	f.payloads[jobID] = payload
	return nil
}

func fixedClock() string { return "2026-07-25" }

func TestAggregate(t *testing.T) {
	jobs := []Job{
		{ModelID: "amazon.nova-lite-v1:0", CustomPrompt: "サイバーパンク風", InputTokens: 100, OutputTokens: 50},
		{ModelID: "amazon.nova-lite-v1:0", CustomPrompt: "サイバーパンク風", InputTokens: 200, OutputTokens: 60},
		{ModelID: "deepseek.v3.2", CustomPrompt: "  太宰治風  ", InputTokens: 10, OutputTokens: 5},
		// カスタムプロンプト未指定は傾向に数えない。
		{ModelID: "deepseek.v3.2", CustomPrompt: "   ", InputTokens: 1, OutputTokens: 2},
	}

	m := Aggregate(jobs)

	if m.TotalJobs != 4 {
		t.Errorf("TotalJobs = %d, want 4", m.TotalJobs)
	}

	// 件数降順。同数はモデル ID 昇順で決定的に並ぶ。
	if len(m.ModelUsage) != 2 {
		t.Fatalf("ModelUsage 件数 = %d, want 2", len(m.ModelUsage))
	}
	for _, mu := range m.ModelUsage {
		if mu.Count != 2 {
			t.Errorf("%s の Count = %d, want 2", mu.ModelID, mu.Count)
		}
		if mu.Ratio != 0.5 {
			t.Errorf("%s の Ratio = %v, want 0.5", mu.ModelID, mu.Ratio)
		}
	}
	if m.ModelUsage[0].ModelID != "amazon.nova-lite-v1:0" {
		t.Errorf("同数時はモデル ID 昇順を期待したが: %q", m.ModelUsage[0].ModelID)
	}

	// 前後の空白を除いた上で数え、空白のみは除外する。
	if len(m.PromptTrends) != 2 {
		t.Fatalf("PromptTrends 件数 = %d, want 2", len(m.PromptTrends))
	}
	if m.PromptTrends[0].Prompt != "サイバーパンク風" || m.PromptTrends[0].Count != 2 {
		t.Errorf("PromptTrends[0] = %+v", m.PromptTrends[0])
	}
	if m.PromptTrends[1].Prompt != "太宰治風" {
		t.Errorf("空白はトリムして数える。got %q", m.PromptTrends[1].Prompt)
	}

	want := TokenUsage{InputTokens: 311, OutputTokens: 117, TotalTokens: 428}
	if m.TokenUsage != want {
		t.Errorf("TokenUsage = %+v, want %+v", m.TokenUsage, want)
	}
}

func TestAggregate_Empty(t *testing.T) {
	m := Aggregate(nil)

	if m.TotalJobs != 0 {
		t.Errorf("TotalJobs = %d, want 0", m.TotalJobs)
	}
	// 0 件でもゼロ除算せず、空の集計として成立する。
	if len(m.ModelUsage) != 0 || len(m.PromptTrends) != 0 {
		t.Errorf("空入力で要素が生成された: %+v", m)
	}
	if m.TokenUsage != (TokenUsage{}) {
		t.Errorf("TokenUsage = %+v, want ゼロ値", m.TokenUsage)
	}
}

func TestAggregate_PromptTrendsAreLimited(t *testing.T) {
	// 上位 PromptTrendLimit 件に丸められることを確認する。
	jobs := make([]Job, 0, PromptTrendLimit+5)
	for i := 0; i < PromptTrendLimit+5; i++ {
		jobs = append(jobs, Job{CustomPrompt: string(rune('a' + i))})
	}

	m := Aggregate(jobs)

	if len(m.PromptTrends) != PromptTrendLimit {
		t.Errorf("PromptTrends 件数 = %d, want %d", len(m.PromptTrends), PromptTrendLimit)
	}
}

func TestHandle_Scan(t *testing.T) {
	want := []Job{{ModelID: "deepseek.v3.2"}}
	h := New(&fakeScanner{jobs: want}, &fakeWriter{}, fixedClock)

	got, err := h.Handle(context.Background(), Event{Phase: PhaseScan})
	if err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}
	jobs, ok := got.([]Job)
	if !ok {
		t.Fatalf("戻り値の型 = %T, want []Job", got)
	}
	if len(jobs) != 1 || jobs[0].ModelID != "deepseek.v3.2" {
		t.Errorf("jobs = %+v", jobs)
	}
}

func TestHandle_ScanError(t *testing.T) {
	sentinel := errors.New("scan 失敗")
	h := New(&fakeScanner{err: sentinel}, &fakeWriter{}, fixedClock)

	if _, err := h.Handle(context.Background(), Event{Phase: PhaseScan}); !errors.Is(err, sentinel) {
		t.Errorf("元のエラーをラップして返すことを期待したが: %v", err)
	}
}

func TestHandle_Aggregate(t *testing.T) {
	h := New(&fakeScanner{}, &fakeWriter{}, fixedClock)
	ev := Event{Phase: PhaseAggregate, Scan: []Job{{ModelID: "x", InputTokens: 3}}}

	got, err := h.Handle(context.Background(), ev)
	if err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}
	m, ok := got.(Metrics)
	if !ok {
		t.Fatalf("戻り値の型 = %T, want Metrics", got)
	}
	if m.TotalJobs != 1 || m.TokenUsage.InputTokens != 3 {
		t.Errorf("metrics = %+v", m)
	}
}

func TestHandle_Write(t *testing.T) {
	w := &fakeWriter{}
	h := New(&fakeScanner{}, w, fixedClock)
	m := Metrics{TotalJobs: 2, TokenUsage: TokenUsage{TotalTokens: 9}}

	got, err := h.Handle(context.Background(), Event{Phase: PhaseWrite, Metrics: &m})
	if err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}

	// SPEC §4③ のキー形式 "STATS#<date>#<metric>" で 3 指標を書き込む。
	want := []string{
		"STATS#2026-07-25#model_usage",
		"STATS#2026-07-25#prompt_trends",
		"STATS#2026-07-25#token_usage",
	}
	if len(w.keys) != len(want) {
		t.Fatalf("書き込みキー数 = %d, want %d (%v)", len(w.keys), len(want), w.keys)
	}
	for i, k := range want {
		if w.keys[i] != k {
			t.Errorf("keys[%d] = %q, want %q", i, w.keys[i], k)
		}
	}

	res, ok := got.(WriteResult)
	if !ok {
		t.Fatalf("戻り値の型 = %T, want WriteResult", got)
	}
	if res.Date != "2026-07-25" || len(res.Written) != 3 {
		t.Errorf("WriteResult = %+v", res)
	}
}

func TestHandle_WriteError(t *testing.T) {
	sentinel := errors.New("put 失敗")
	h := New(&fakeScanner{}, &fakeWriter{err: sentinel}, fixedClock)

	_, err := h.Handle(context.Background(), Event{Phase: PhaseWrite, Metrics: &Metrics{}})
	if !errors.Is(err, sentinel) {
		t.Errorf("元のエラーをラップして返すことを期待したが: %v", err)
	}
}

func TestHandle_WriteWithoutMetrics(t *testing.T) {
	h := New(&fakeScanner{}, &fakeWriter{}, fixedClock)

	// metrics 欠落で黙って空レコードを書かないこと。
	if _, err := h.Handle(context.Background(), Event{Phase: PhaseWrite}); err == nil {
		t.Error("metrics 欠落でエラーを期待したが nil")
	}
}

func TestHandle_UnknownPhase(t *testing.T) {
	h := New(&fakeScanner{}, &fakeWriter{}, fixedClock)

	_, err := h.Handle(context.Background(), Event{Phase: "publish"})
	if !errors.Is(err, ErrUnknownPhase) {
		t.Errorf("ErrUnknownPhase を期待したが: %v", err)
	}
}
