// Command lambda-stats は日次の集計バッチを担う Lambda（SPEC §4④）。
//
// Step Functions の Scan / Aggregate / Write の各 Task から phase 指定で
// 呼び出される単一の関数として動作する。依存（DynamoDB / 時刻）をここで結線し、
// フェーズ処理は internal/stats に委譲する。テーブル名は環境変数から読み取り、
// ハードコードしない（SPEC §4④）。
package main

import (
	"context"
	"log"
	"os"
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"

	"github.com/ojos/code-narrative/apps/lambda-stats/internal/stats"
	"github.com/ojos/code-narrative/apps/lambda-stats/internal/store"
)

// 環境変数キー。
const envTableName = "DYNAMODB_TABLE"

func main() {
	ctx := context.Background()

	tableName := os.Getenv(envTableName)
	if tableName == "" {
		log.Fatalf("環境変数 %s が未設定です", envTableName)
	}

	// リージョンは AWS SDK が AWS_REGION 等の環境変数から解決する。
	awsCfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		log.Fatalf("AWS 設定の読み込みに失敗: %v", err)
	}

	st := store.New(dynamodb.NewFromConfig(awsCfg), tableName)
	h := stats.New(st, st, utcDate)

	lambda.Start(h.Handle)
}

// utcDate は集計日（UTC の YYYY-MM-DD）を返す。
//
// 集計結果のキー "STATS#<date>#<metric>" に用いる。実行環境のローカルタイムに
// 依存すると同じ実行が別日付になり得るため UTC に固定する。
func utcDate() string {
	return time.Now().UTC().Format("2006-01-02")
}
