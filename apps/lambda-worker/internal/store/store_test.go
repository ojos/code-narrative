package store

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
)

// fakeDynamo は DynamoAPI のテスト用実装。
type fakeDynamo struct {
	err    error
	inputs []*dynamodb.UpdateItemInput
}

func (f *fakeDynamo) UpdateItem(_ context.Context, in *dynamodb.UpdateItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error) {
	f.inputs = append(f.inputs, in)
	if f.err != nil {
		return nil, f.err
	}
	return &dynamodb.UpdateItemOutput{}, nil
}

// newStore は時刻を固定した Store を生成する。
func newStore(api DynamoAPI) *Store {
	s := New(api, "CodeNarratives")
	s.now = func() time.Time { return time.Date(2026, 7, 25, 0, 0, 0, 0, time.UTC) }
	return s
}

// leaseEvalDynamo は保持レコードに対してリース条件式を実際に評価する fake。
//
// DynamoDB のサーバ側条件評価を模し、stale / fresh の分岐を行動レベルで検証する。
// 対応するのは MarkProcessing のリース条件のみ。
type leaseEvalDynamo struct {
	status       string
	updatedAt    string
	updatedCount int
}

func (f *leaseEvalDynamo) UpdateItem(_ context.Context, in *dynamodb.UpdateItemInput, _ ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error) {
	cutoff := in.ExpressionAttributeValues[":cutoff"].(*ddbtypes.AttributeValueMemberS).Value
	now := in.ExpressionAttributeValues[":now"].(*ddbtypes.AttributeValueMemberS).Value

	// #status = :queued OR (#status = :processing AND #updated_at < :cutoff)
	acquirable := f.status == statusQueued ||
		(f.status == statusProcessing && f.updatedAt < cutoff)
	if !acquirable {
		return nil, &ddbtypes.ConditionalCheckFailedException{}
	}
	f.status = statusProcessing
	f.updatedAt = now
	f.updatedCount++
	return &dynamodb.UpdateItemOutput{}, nil
}

// sVal は文字列属性値を取り出す。
func sVal(t *testing.T, av ddbtypes.AttributeValue) string {
	t.Helper()
	s, ok := av.(*ddbtypes.AttributeValueMemberS)
	if !ok {
		t.Fatalf("string 属性ではない: %T", av)
	}
	return s.Value
}

const testCutoff = "2026-07-25T00:00:00Z"

// TestMarkProcessing_AcquiresLease は queued または stale な processing を獲得できる
// 場合（DynamoDB が条件成立で成功を返す場合）、リース方式の条件式・cutoff・更新後の
// status/updated_at が正しく組み立てられることを検証する。
func TestMarkProcessing_AcquiresLease(t *testing.T) {
	fake := &fakeDynamo{}
	s := newStore(fake)

	if err := s.MarkProcessing(context.Background(), "job-1", testCutoff); err != nil {
		t.Fatalf("MarkProcessing: %v", err)
	}
	if len(fake.inputs) != 1 {
		t.Fatalf("UpdateItem 呼び出し数 = %d", len(fake.inputs))
	}
	in := fake.inputs[0]

	wantCond := "#status = :queued OR (#status = :processing AND #updated_at < :cutoff)"
	if aws.ToString(in.ConditionExpression) != wantCond {
		t.Errorf("ConditionExpression = %q", aws.ToString(in.ConditionExpression))
	}
	if in.ExpressionAttributeNames["#updated_at"] != "updated_at" {
		t.Errorf("#updated_at のマッピングが無い: %v", in.ExpressionAttributeNames)
	}
	if got := sVal(t, in.ExpressionAttributeValues[":cutoff"]); got != testCutoff {
		t.Errorf(":cutoff = %q", got)
	}
	if got := sVal(t, in.ExpressionAttributeValues[":processing"]); got != statusProcessing {
		t.Errorf(":processing = %q", got)
	}
	// updated_at は now（固定 2026-07-25T00:00:00Z）でリース更新される。
	if got := sVal(t, in.ExpressionAttributeValues[":now"]); got != "2026-07-25T00:00:00Z" {
		t.Errorf(":now = %q", got)
	}
}

// TestMarkProcessing_FreshLeaseSkips は processing リースが有効（fresh）または
// 既に completed/failed のとき、DynamoDB が条件不成立を返し ErrAlreadyProcessing に
// 変換されること（従来の冪等スキップ）を検証する。
func TestMarkProcessing_FreshLeaseSkips(t *testing.T) {
	fake := &fakeDynamo{err: &ddbtypes.ConditionalCheckFailedException{}}
	s := newStore(fake)

	err := s.MarkProcessing(context.Background(), "job-1", testCutoff)
	if !errors.Is(err, ErrAlreadyProcessing) {
		t.Fatalf("ErrAlreadyProcessing を期待したが: %v", err)
	}
}

// TestMarkProcessing_ProcessingFreshBehavioral は、processing かつ updated_at が
// cutoff 以降（fresh）のジョブに対し、条件を実評価してスキップ（ErrAlreadyProcessing）
// されることを検証する（再配信2回目・リース有効ケース）。
func TestMarkProcessing_ProcessingFreshBehavioral(t *testing.T) {
	cutoff := "2026-07-25T00:00:00Z"
	fake := &leaseEvalDynamo{status: statusProcessing, updatedAt: "2026-07-25T00:05:00Z"} // cutoff より後 = fresh
	s := newStore(fake)

	err := s.MarkProcessing(context.Background(), "job-1", cutoff)
	if !errors.Is(err, ErrAlreadyProcessing) {
		t.Fatalf("fresh リースはスキップされるべき: %v", err)
	}
	if fake.updatedCount != 0 {
		t.Error("fresh リースでレコードを更新してはならない")
	}
}

// TestMarkProcessing_ProcessingStaleBehavioral は、processing かつ updated_at が
// cutoff より前（stale=リース失効）のジョブに対し、条件を実評価して再取得が
// 成功し、updated_at がリース更新されることを検証する（一時障害の取り残し回収）。
func TestMarkProcessing_ProcessingStaleBehavioral(t *testing.T) {
	cutoff := "2026-07-25T00:00:00Z"
	fake := &leaseEvalDynamo{status: statusProcessing, updatedAt: "2026-07-24T23:00:00Z"} // cutoff より前 = stale
	s := newStore(fake)

	if err := s.MarkProcessing(context.Background(), "job-1", cutoff); err != nil {
		t.Fatalf("stale リースは再取得成功すべき: %v", err)
	}
	if fake.updatedCount != 1 {
		t.Fatalf("再取得でレコードが更新されるべき: count=%d", fake.updatedCount)
	}
	if fake.updatedAt != "2026-07-25T00:00:00Z" {
		t.Errorf("updated_at がリース更新されていない: %q", fake.updatedAt)
	}
}

func TestMarkFailed_RecordsMessage(t *testing.T) {
	fake := &fakeDynamo{}
	s := newStore(fake)

	if err := s.MarkFailed(context.Background(), "job-1", "サイズ超過: 200MB"); err != nil {
		t.Fatalf("MarkFailed: %v", err)
	}
	in := fake.inputs[0]
	if got := sVal(t, in.ExpressionAttributeValues[":failed"]); got != statusFailed {
		t.Errorf(":failed = %q", got)
	}
	if got := sVal(t, in.ExpressionAttributeValues[":msg"]); got != "サイズ超過: 200MB" {
		t.Errorf("error_message = %q", got)
	}
}

func TestMarkCompleted_WritesResultAndUsage(t *testing.T) {
	fake := &fakeDynamo{}
	s := newStore(fake)

	err := s.MarkCompleted(context.Background(), "job-1", CompletedResult{
		Story:      "物語",
		RepoDigest: "tree",
		ModelID:    "amazon.nova-lite-v1:0",
		Usage:      model.Usage{InputTokens: 100, OutputTokens: 200},
	})
	if err != nil {
		t.Fatalf("MarkCompleted: %v", err)
	}
	in := fake.inputs[0]
	if got := sVal(t, in.ExpressionAttributeValues[":completed"]); got != statusCompleted {
		t.Errorf(":completed = %q", got)
	}
	if got := sVal(t, in.ExpressionAttributeValues[":story"]); got != "物語" {
		t.Errorf(":story = %q", got)
	}
	usage, ok := in.ExpressionAttributeValues[":usage"].(*ddbtypes.AttributeValueMemberM)
	if !ok {
		t.Fatalf(":usage が Map ではない")
	}
	in100 := usage.Value["input_tokens"].(*ddbtypes.AttributeValueMemberN)
	if in100.Value != "100" {
		t.Errorf("input_tokens = %q", in100.Value)
	}
}

func TestMarkCompleted_PropagatesError(t *testing.T) {
	fake := &fakeDynamo{err: errors.New("throttled")}
	s := newStore(fake)

	err := s.MarkCompleted(context.Background(), "job-1", CompletedResult{})
	if err == nil {
		t.Fatal("DynamoDB エラーが伝播すべき")
	}
}
