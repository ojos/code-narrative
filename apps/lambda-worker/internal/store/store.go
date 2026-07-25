// Package store は DynamoDB への変換ジョブ状態の永続化を担う。
//
// SPEC §4③ のスキーマに従い、job_id をキーとしてジョブレコードの
// status 遷移（queued → processing → completed / failed）を書き込む。
// 冪等性は processing 遷移時の ConditionExpression で担保する。
package store

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
)

// ジョブの状態値（SPEC §4③）。
const (
	statusQueued     = "queued"
	statusProcessing = "processing"
	statusCompleted  = "completed"
	statusFailed     = "failed"
)

// ErrAlreadyProcessing は status が queued 以外のため processing へ遷移できなかった
// 場合に返る（at-least-once 配信での二重処理を冪等にスキップするための番兵）。
var ErrAlreadyProcessing = errors.New("ジョブは既に処理済みまたは処理中です")

// DynamoAPI は本パッケージが必要とする DynamoDB 操作の最小インターフェイス。
//
// *dynamodb.Client を差し替え可能にし、単体テストで実 AWS へ接続せずに検証する。
type DynamoAPI interface {
	UpdateItem(ctx context.Context, params *dynamodb.UpdateItemInput, optFns ...func(*dynamodb.Options)) (*dynamodb.UpdateItemOutput, error)
}

// Store は DynamoDB 上のジョブレコードを操作する。
type Store struct {
	api       DynamoAPI
	tableName string
	// now は現在時刻取得関数（テストで固定するため注入可能）。
	now func() time.Time
}

// New は DynamoAPI 実装とテーブル名から Store を生成する。
func New(api DynamoAPI, tableName string) *Store {
	return &Store{api: api, tableName: tableName, now: time.Now}
}

// nowISO は現在時刻を ISO8601（UTC）文字列で返す。
func (s *Store) nowISO() string {
	return s.now().UTC().Format(time.RFC3339)
}

// MarkProcessing は status が queued の場合のみ processing へ条件付き更新する。
//
// 条件不一致（既に processing/completed/failed）の場合は ErrAlreadyProcessing を返す。
func (s *Store) MarkProcessing(ctx context.Context, jobID string) error {
	_, err := s.api.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName:           aws.String(s.tableName),
		Key:                 keyOf(jobID),
		UpdateExpression:    aws.String("SET #status = :processing, updated_at = :now"),
		ConditionExpression: aws.String("#status = :queued"),
		ExpressionAttributeNames: map[string]string{
			"#status": "status",
		},
		ExpressionAttributeValues: map[string]ddbtypes.AttributeValue{
			":processing": &ddbtypes.AttributeValueMemberS{Value: statusProcessing},
			":queued":     &ddbtypes.AttributeValueMemberS{Value: statusQueued},
			":now":        &ddbtypes.AttributeValueMemberS{Value: s.nowISO()},
		},
	})
	if err != nil {
		var condErr *ddbtypes.ConditionalCheckFailedException
		if errors.As(err, &condErr) {
			return ErrAlreadyProcessing
		}
		return fmt.Errorf("processing への条件付き更新に失敗: %w", err)
	}
	return nil
}

// CompletedResult は完了時に書き込む生成結果一式を表す。
type CompletedResult struct {
	// Story は生成されたショートショート本文。
	Story string
	// RepoDigest は抽出要旨（ディレクトリツリー + 選定ファイル名一覧）。
	RepoDigest string
	// ModelID は実際に使用したモデル ID。
	ModelID string
	// Usage はトークン使用量。
	Usage model.Usage
}

// MarkCompleted は status を completed とし、生成結果・要旨・使用モデル・
// トークン使用量を書き込む。ファイル全文は保存しない（SPEC §4② サイズ制限）。
func (s *Store) MarkCompleted(ctx context.Context, jobID string, res CompletedResult) error {
	_, err := s.api.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName: aws.String(s.tableName),
		Key:       keyOf(jobID),
		UpdateExpression: aws.String(
			"SET #status = :completed, generated_story = :story, repo_digest = :digest, " +
				"model_id = :model, #usage = :usage, updated_at = :now"),
		ExpressionAttributeNames: map[string]string{
			"#status": "status",
			"#usage":  "usage",
		},
		ExpressionAttributeValues: map[string]ddbtypes.AttributeValue{
			":completed": &ddbtypes.AttributeValueMemberS{Value: statusCompleted},
			":story":     &ddbtypes.AttributeValueMemberS{Value: res.Story},
			":digest":    &ddbtypes.AttributeValueMemberS{Value: res.RepoDigest},
			":model":     &ddbtypes.AttributeValueMemberS{Value: res.ModelID},
			":usage":     usageAttr(res.Usage),
			":now":       &ddbtypes.AttributeValueMemberS{Value: s.nowISO()},
		},
	})
	if err != nil {
		return fmt.Errorf("completed の書き込みに失敗: %w", err)
	}
	return nil
}

// MarkFailed は status を failed とし、error_message に失敗理由を記録する。
func (s *Store) MarkFailed(ctx context.Context, jobID, errMessage string) error {
	_, err := s.api.UpdateItem(ctx, &dynamodb.UpdateItemInput{
		TableName:        aws.String(s.tableName),
		Key:              keyOf(jobID),
		UpdateExpression: aws.String("SET #status = :failed, error_message = :msg, updated_at = :now"),
		ExpressionAttributeNames: map[string]string{
			"#status": "status",
		},
		ExpressionAttributeValues: map[string]ddbtypes.AttributeValue{
			":failed": &ddbtypes.AttributeValueMemberS{Value: statusFailed},
			":msg":    &ddbtypes.AttributeValueMemberS{Value: errMessage},
			":now":    &ddbtypes.AttributeValueMemberS{Value: s.nowISO()},
		},
	})
	if err != nil {
		return fmt.Errorf("failed の書き込みに失敗: %w", err)
	}
	return nil
}

// keyOf は job_id をパーティションキーとする Key 表現を返す。
func keyOf(jobID string) map[string]ddbtypes.AttributeValue {
	return map[string]ddbtypes.AttributeValue{
		"job_id": &ddbtypes.AttributeValueMemberS{Value: jobID},
	}
}

// usageAttr は Usage を DynamoDB の Map 属性（数値メンバ）へ変換する。
func usageAttr(u model.Usage) ddbtypes.AttributeValue {
	return &ddbtypes.AttributeValueMemberM{
		Value: map[string]ddbtypes.AttributeValue{
			"input_tokens":  &ddbtypes.AttributeValueMemberN{Value: strconv.FormatInt(int64(u.InputTokens), 10)},
			"output_tokens": &ddbtypes.AttributeValueMemberN{Value: strconv.FormatInt(int64(u.OutputTokens), 10)},
		},
	}
}
