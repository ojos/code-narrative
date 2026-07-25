// Command lambda-worker は SQS をトリガーに GitHub リポジトリを解析し、
// Amazon Bedrock でショートショートを生成して DynamoDB へ格納する Lambda ワーカー。
//
// 依存の実装（DynamoDB / GitHub / Bedrock）をここで結線し、以降の
// オーケストレーションは internal/worker に委譲する。テーブル名などの設定は
// 環境変数から読み取り、ハードコードしない（SPEC §4②）。
package main

import (
	"context"
	"log"
	"os"
	"strconv"
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/bedrock"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/extract"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/ghclient"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/store"
	"github.com/ojos/code-narrative/apps/lambda-worker/internal/worker"
)

// 環境変数キー。
const (
	envTableName   = "DYNAMODB_TABLE"
	envGitHubToken = "GITHUB_TOKEN"
	envLeaseSecs   = "PROCESSING_LEASE_SECONDS"
)

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
	fetcher := ghclient.New(os.Getenv(envGitHubToken)) // トークン任意
	gen := bedrock.NewGenerator(bedrockruntime.NewFromConfig(awsCfg))

	cfg := worker.DefaultConfig()
	cfg.ProcessingLease = leaseFromEnv(cfg.ProcessingLease)

	w := worker.New(st, fetcher, extract.Service{}, gen, cfg)
	lambda.Start(w.Handle)
}

// leaseFromEnv は環境変数 PROCESSING_LEASE_SECONDS（秒）を読み取り、
// 未設定・不正・非正の場合は fallback を返す。
func leaseFromEnv(fallback time.Duration) time.Duration {
	raw := os.Getenv(envLeaseSecs)
	if raw == "" {
		return fallback
	}
	secs, err := strconv.Atoi(raw)
	if err != nil || secs <= 0 {
		log.Printf("環境変数 %s が不正（%q）のため既定値を使用します", envLeaseSecs, raw)
		return fallback
	}
	return time.Duration(secs) * time.Second
}
