package store

import (
	"context"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"github.com/ojos/code-narrative/apps/lambda-stats/internal/stats"
)

// fakeDynamo は DynamoAPI のテスト代替。Scan は用意した応答を順に返す。
type fakeDynamo struct {
	scanOuts []*dynamodb.ScanOutput
	scanIn   []*dynamodb.ScanInput
	scanErr  error

	putIn  []*dynamodb.PutItemInput
	putErr error
}

func (f *fakeDynamo) Scan(_ context.Context, in *dynamodb.ScanInput, _ ...func(*dynamodb.Options)) (*dynamodb.ScanOutput, error) {
	if f.scanErr != nil {
		return nil, f.scanErr
	}
	f.scanIn = append(f.scanIn, in)
	out := f.scanOuts[0]
	f.scanOuts = f.scanOuts[1:]
	return out, nil
}

func (f *fakeDynamo) PutItem(_ context.Context, in *dynamodb.PutItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error) {
	if f.putErr != nil {
		return nil, f.putErr
	}
	f.putIn = append(f.putIn, in)
	return &dynamodb.PutItemOutput{}, nil
}

func s(v string) ddbtypes.AttributeValue { return &ddbtypes.AttributeValueMemberS{Value: v} }
func n(v string) ddbtypes.AttributeValue { return &ddbtypes.AttributeValueMemberN{Value: v} }

func TestScanJobs_ExcludesStatsRecords(t *testing.T) {
	fake := &fakeDynamo{scanOuts: []*dynamodb.ScanOutput{{
		Items: []map[string]ddbtypes.AttributeValue{
			{"job_id": s("job-1"), "status": s("completed"), "model_id": s("deepseek.v3.2")},
			// 前回の集計結果。母数へ混入させない。
			{"job_id": s("STATS#2026-07-24#model_usage")},
			{"job_id": s("job-2"), "status": s("failed"), "model_id": s("amazon.nova-lite-v1:0")},
		},
	}}}

	jobs, err := New(fake, "T").ScanJobs(context.Background())
	if err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}
	if len(jobs) != 2 {
		t.Fatalf("件数 = %d, want 2 (STATS# を除外): %+v", len(jobs), jobs)
	}
	if jobs[0].ModelID != "deepseek.v3.2" || jobs[1].ModelID != "amazon.nova-lite-v1:0" {
		t.Errorf("jobs = %+v", jobs)
	}
}

func TestScanJobs_ParsesUsageTokens(t *testing.T) {
	fake := &fakeDynamo{scanOuts: []*dynamodb.ScanOutput{{
		Items: []map[string]ddbtypes.AttributeValue{
			{
				"job_id":        s("job-1"),
				"custom_prompt": s("童話風"),
				"usage": &ddbtypes.AttributeValueMemberM{Value: map[string]ddbtypes.AttributeValue{
					"input_tokens":  n("120"),
					"output_tokens": n("34"),
				}},
			},
			// usage 欠落（未完了ジョブ）はゼロとして扱い、集計を止めない。
			{"job_id": s("job-2")},
		},
	}}}

	jobs, err := New(fake, "T").ScanJobs(context.Background())
	if err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}
	if jobs[0].InputTokens != 120 || jobs[0].OutputTokens != 34 {
		t.Errorf("jobs[0] = %+v", jobs[0])
	}
	if jobs[0].CustomPrompt != "童話風" {
		t.Errorf("custom_prompt = %q", jobs[0].CustomPrompt)
	}
	if jobs[1].InputTokens != 0 || jobs[1].OutputTokens != 0 {
		t.Errorf("usage 欠落はゼロを期待したが: %+v", jobs[1])
	}
}

func TestScanJobs_FollowsPagination(t *testing.T) {
	// 1 ページで打ち切ると 1MB 超のテーブルで集計が静かに不完全になる。
	fake := &fakeDynamo{scanOuts: []*dynamodb.ScanOutput{
		{
			Items:            []map[string]ddbtypes.AttributeValue{{"job_id": s("job-1")}},
			LastEvaluatedKey: map[string]ddbtypes.AttributeValue{"job_id": s("job-1")},
		},
		{
			Items: []map[string]ddbtypes.AttributeValue{{"job_id": s("job-2")}},
		},
	}}

	jobs, err := New(fake, "T").ScanJobs(context.Background())
	if err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}
	if len(jobs) != 2 {
		t.Fatalf("件数 = %d, want 2（2 ページ分）", len(jobs))
	}
	if len(fake.scanIn) != 2 {
		t.Fatalf("Scan 呼び出し数 = %d, want 2", len(fake.scanIn))
	}
	if fake.scanIn[1].ExclusiveStartKey == nil {
		t.Error("2 回目の Scan に ExclusiveStartKey が渡っていない")
	}
}

func TestScanJobs_ProjectsWithReservedWordAliases(t *testing.T) {
	fake := &fakeDynamo{scanOuts: []*dynamodb.ScanOutput{{}}}

	if _, err := New(fake, "T").ScanJobs(context.Background()); err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}

	in := fake.scanIn[0]
	if aws.ToString(in.TableName) != "T" {
		t.Errorf("TableName = %q", aws.ToString(in.TableName))
	}
	// status は DynamoDB の予約語。実名で射影すると ValidationException になる。
	if got := in.ExpressionAttributeNames["#status"]; got != "status" {
		t.Errorf("#status のマッピング = %q", got)
	}
	if aws.ToString(in.ProjectionExpression) == "" {
		t.Error("ProjectionExpression が未設定（全属性取得はペイロード肥大の原因）")
	}
}

func TestScanJobs_ReturnsNonNilWhenEmpty(t *testing.T) {
	// 0 件で nil を返すと JSON で null になり、aggregate 側の「scan 欠落」検出に
	// 誤検知する（ジョブ 0 件の正常系が payload エラーとして落ちる）。
	fake := &fakeDynamo{scanOuts: []*dynamodb.ScanOutput{{}}}

	jobs, err := New(fake, "T").ScanJobs(context.Background())
	if err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}
	if jobs == nil {
		t.Error("0 件でも非 nil の空スライスを期待したが nil")
	}
	if len(jobs) != 0 {
		t.Errorf("件数 = %d, want 0", len(jobs))
	}
}

func TestScanJobs_Error(t *testing.T) {
	sentinel := errors.New("scan 失敗")
	fake := &fakeDynamo{scanErr: sentinel}

	if _, err := New(fake, "T").ScanJobs(context.Background()); !errors.Is(err, sentinel) {
		t.Errorf("元のエラーをラップして返すことを期待したが: %v", err)
	}
}

func TestPutMetric(t *testing.T) {
	fake := &fakeDynamo{}

	payload := map[string]any{"total_jobs": 3}
	if err := New(fake, "T").PutMetric(context.Background(), "STATS#2026-07-25#model_usage", payload); err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}

	if len(fake.putIn) != 1 {
		t.Fatalf("PutItem 呼び出し数 = %d, want 1", len(fake.putIn))
	}
	item := fake.putIn[0].Item
	got, ok := item["job_id"].(*ddbtypes.AttributeValueMemberS)
	if !ok || got.Value != "STATS#2026-07-25#model_usage" {
		t.Errorf("job_id = %+v", item["job_id"])
	}
	if _, ok := item["metric"]; !ok {
		t.Error("metric 属性が書き込まれていない")
	}
}

// TestPutMetric_WritesSnakeCaseKeys は集計レコードの属性名を snake_case に固定する。
//
// attributevalue.Marshal は json タグへフォールバックしないため、dynamodbav タグを
// 落とすとフィールド名そのまま(PascalCase)で書き込まれる。テーブル内の他属性は
// snake_case のため、集計レコードだけキー命名が食い違い、読み手側で静かに欠落する。
func TestPutMetric_WritesSnakeCaseKeys(t *testing.T) {
	fake := &fakeDynamo{}

	payload := map[string]any{
		"total_jobs": int64(2),
		"items": []stats.ModelUsage{
			{ModelID: "deepseek.v3.2", Count: 2, Ratio: 1.0},
		},
	}
	if err := New(fake, "T").PutMetric(context.Background(), "STATS#2026-07-25#model_usage", payload); err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}

	metric, ok := fake.putIn[0].Item["metric"].(*ddbtypes.AttributeValueMemberM)
	if !ok {
		t.Fatalf("metric の型 = %T, want M", fake.putIn[0].Item["metric"])
	}
	items, ok := metric.Value["items"].(*ddbtypes.AttributeValueMemberL)
	if !ok {
		t.Fatalf("items の型 = %T, want L", metric.Value["items"])
	}
	first, ok := items.Value[0].(*ddbtypes.AttributeValueMemberM)
	if !ok {
		t.Fatalf("items[0] の型 = %T, want M", items.Value[0])
	}

	for _, key := range []string{"model_id", "count", "ratio"} {
		if _, ok := first.Value[key]; !ok {
			got := make([]string, 0, len(first.Value))
			for k := range first.Value {
				got = append(got, k)
			}
			t.Errorf("属性 %q が無い。実際のキー: %v (dynamodbav タグ漏れの可能性)", key, got)
		}
	}
}

func TestPutMetric_TokenUsageKeys(t *testing.T) {
	fake := &fakeDynamo{}

	usage := stats.TokenUsage{InputTokens: 10, OutputTokens: 20, TotalTokens: 30}
	if err := New(fake, "T").PutMetric(context.Background(), "STATS#2026-07-25#token_usage", usage); err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}

	metric, ok := fake.putIn[0].Item["metric"].(*ddbtypes.AttributeValueMemberM)
	if !ok {
		t.Fatalf("metric の型 = %T, want M", fake.putIn[0].Item["metric"])
	}
	for _, key := range []string{"input_tokens", "output_tokens", "total_tokens"} {
		if _, ok := metric.Value[key]; !ok {
			t.Errorf("属性 %q が無い (dynamodbav タグ漏れの可能性)", key)
		}
	}
}

func TestPutMetric_Error(t *testing.T) {
	sentinel := errors.New("put 失敗")
	fake := &fakeDynamo{putErr: sentinel}

	err := New(fake, "T").PutMetric(context.Background(), "STATS#2026-07-25#token_usage", map[string]any{})
	if !errors.Is(err, sentinel) {
		t.Errorf("元のエラーをラップして返すことを期待したが: %v", err)
	}
}
