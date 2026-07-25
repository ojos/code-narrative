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

// sVal は文字列属性値を取り出す。
func sVal(t *testing.T, av ddbtypes.AttributeValue) string {
	t.Helper()
	s, ok := av.(*ddbtypes.AttributeValueMemberS)
	if !ok {
		t.Fatalf("string 属性ではない: %T", av)
	}
	return s.Value
}

func TestMarkProcessing_Success(t *testing.T) {
	fake := &fakeDynamo{}
	s := newStore(fake)

	if err := s.MarkProcessing(context.Background(), "job-1"); err != nil {
		t.Fatalf("MarkProcessing: %v", err)
	}
	if len(fake.inputs) != 1 {
		t.Fatalf("UpdateItem 呼び出し数 = %d", len(fake.inputs))
	}
	in := fake.inputs[0]
	if aws.ToString(in.ConditionExpression) != "#status = :queued" {
		t.Errorf("ConditionExpression = %q", aws.ToString(in.ConditionExpression))
	}
	if got := sVal(t, in.ExpressionAttributeValues[":processing"]); got != statusProcessing {
		t.Errorf(":processing = %q", got)
	}
}

func TestMarkProcessing_ConditionFailed(t *testing.T) {
	fake := &fakeDynamo{err: &ddbtypes.ConditionalCheckFailedException{}}
	s := newStore(fake)

	err := s.MarkProcessing(context.Background(), "job-1")
	if !errors.Is(err, ErrAlreadyProcessing) {
		t.Fatalf("ErrAlreadyProcessing を期待したが: %v", err)
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
