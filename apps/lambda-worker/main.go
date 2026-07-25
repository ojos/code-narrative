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

	w := worker.New(st, fetcher, extract.Service{}, gen, worker.DefaultConfig())
	lambda.Start(w.Handle)
}
