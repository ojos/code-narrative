// Package store は集計バッチの DynamoDB アクセスを担う（SPEC §4③/§4④）。
//
// 変換ジョブの Scan と、集計結果（job_id = "STATS#<date>#<metric>"）の
// 書き込みを提供する。
package store

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"

	"github.com/ojos/code-narrative/apps/lambda-stats/internal/stats"
)

// statsKeyPrefix は集計結果レコードの job_id プレフィックス（SPEC §4③）。
const statsKeyPrefix = "STATS#"

// DynamoAPI は本パッケージが用いる DynamoDB 操作の最小インターフェイス。
type DynamoAPI interface {
	Scan(ctx context.Context, params *dynamodb.ScanInput, optFns ...func(*dynamodb.Options)) (*dynamodb.ScanOutput, error)
	PutItem(ctx context.Context, params *dynamodb.PutItemInput, optFns ...func(*dynamodb.Options)) (*dynamodb.PutItemOutput, error)
}

// Store は DynamoDB 上の変換ジョブと集計結果を扱う。
type Store struct {
	api       DynamoAPI
	tableName string
}

// New は Store を生成する。
func New(api DynamoAPI, tableName string) *Store {
	return &Store{api: api, tableName: tableName}
}

// ScanJobs は集計対象の変換ジョブを全件取得する（SPEC §4④）。
//
// 実証規模のため全件 Scan を許容する。集計に使う属性のみを射影し、
// Step Functions のペイロード上限（256KB）に対する余裕を確保する。
// 集計結果レコード（job_id が "STATS#" で始まる）は集計対象から除外する。
// これを含めると、日次実行のたびに前回の集計結果が母数へ混入していく。
func (s *Store) ScanJobs(ctx context.Context) ([]stats.Job, error) {
	var jobs []stats.Job
	var startKey map[string]ddbtypes.AttributeValue

	for {
		out, err := s.api.Scan(ctx, &dynamodb.ScanInput{
			TableName:            aws.String(s.tableName),
			ProjectionExpression: aws.String("#job_id, #status, #model_id, #custom_prompt, #usage"),
			// status は DynamoDB の予約語。他も将来の予約語化に備えて別名で参照する。
			ExpressionAttributeNames: map[string]string{
				"#job_id":        "job_id",
				"#status":        "status",
				"#model_id":      "model_id",
				"#custom_prompt": "custom_prompt",
				"#usage":         "usage",
			},
			ExclusiveStartKey: startKey,
		})
		if err != nil {
			return nil, fmt.Errorf("dynamodb scan に失敗: %w", err)
		}

		for _, item := range out.Items {
			if strings.HasPrefix(stringAttr(item, "job_id"), statsKeyPrefix) {
				continue
			}
			jobs = append(jobs, jobFromItem(item))
		}

		// LastEvaluatedKey が空になるまでページングする。1 ページで打ち切ると
		// テーブルが 1MB を超えた時点で集計が静かに不完全になる。
		if len(out.LastEvaluatedKey) == 0 {
			break
		}
		startKey = out.LastEvaluatedKey
	}
	return jobs, nil
}

// PutMetric は集計結果レコードを書き込む。
func (s *Store) PutMetric(ctx context.Context, jobID string, payload any) error {
	item := map[string]ddbtypes.AttributeValue{
		"job_id": &ddbtypes.AttributeValueMemberS{Value: jobID},
	}
	attr, err := attributevalue.Marshal(payload)
	if err != nil {
		return fmt.Errorf("%s の変換に失敗: %w", jobID, err)
	}
	item["metric"] = attr

	if _, err := s.api.PutItem(ctx, &dynamodb.PutItemInput{
		TableName: aws.String(s.tableName),
		Item:      item,
	}); err != nil {
		return fmt.Errorf("dynamodb putitem に失敗: %w", err)
	}
	return nil
}

// jobFromItem は Scan の 1 項目を集計用の射影へ変換する。
func jobFromItem(item map[string]ddbtypes.AttributeValue) stats.Job {
	j := stats.Job{
		Status:       stringAttr(item, "status"),
		ModelID:      stringAttr(item, "model_id"),
		CustomPrompt: stringAttr(item, "custom_prompt"),
	}
	if usage, ok := item["usage"].(*ddbtypes.AttributeValueMemberM); ok {
		j.InputTokens = numberAttr(usage.Value, "input_tokens")
		j.OutputTokens = numberAttr(usage.Value, "output_tokens")
	}
	return j
}

// stringAttr は文字列属性を取り出す。型が異なる/欠損なら空文字を返す。
func stringAttr(item map[string]ddbtypes.AttributeValue, key string) string {
	if v, ok := item[key].(*ddbtypes.AttributeValueMemberS); ok {
		return v.Value
	}
	return ""
}

// numberAttr は数値属性を取り出す。型が異なる/欠損/解釈不能なら 0 を返す。
func numberAttr(item map[string]ddbtypes.AttributeValue, key string) int64 {
	v, ok := item[key].(*ddbtypes.AttributeValueMemberN)
	if !ok {
		return 0
	}
	n, err := strconv.ParseInt(v.Value, 10, 64)
	if err != nil {
		return 0
	}
	return n
}
