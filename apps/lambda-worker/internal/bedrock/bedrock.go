// Package bedrock は Amazon Bedrock Converse API を用いた物語生成を担う。
//
// model_id のホワイトリスト検証（SPEC §4⑤）と、SPEC §4② のシステムプロンプト /
// User Request 構成による 1 回の Converse 呼び出しを実装する。
package bedrock

import (
	"context"
	"errors"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime"
	brtypes "github.com/aws/aws-sdk-go-v2/service/bedrockruntime/types"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
)

// 既定の推論パラメータ（SPEC §4②）。
const (
	// MaxTokens は生成トークン数の上限（コスト制御）。
	MaxTokens int32 = 2048
	// Temperature は創作用途向けの高めの温度。
	Temperature float32 = 0.8
)

// AllowedModels は呼び出しを許可するモデル ID のホワイトリスト（SPEC §4⑤）。
//
// Anthropic / Meta の近年モデルはクロスリージョン推論プロファイル ID
// （"us." プレフィックス）での呼び出しが必須。
var AllowedModels = map[string]struct{}{
	"us.anthropic.claude-sonnet-4-5-20250929-v1:0": {},
	"amazon.nova-lite-v1:0":                        {},
	"us.meta.llama3-3-70b-instruct-v1:0":           {},
}

// ErrModelNotAllowed はホワイトリスト外の model_id が指定された場合に返る。
var ErrModelNotAllowed = errors.New("model_id がホワイトリストに存在しません")

// ErrEmptyResponse は Converse 応答にテキストが含まれない場合に返る。
var ErrEmptyResponse = errors.New("bedrock 応答にテキストが含まれません")

// ValidateModelID は model_id がホワイトリストに含まれるか検証する。
func ValidateModelID(modelID string) error {
	if _, ok := AllowedModels[modelID]; !ok {
		return fmt.Errorf("%w: %s", ErrModelNotAllowed, modelID)
	}
	return nil
}

// systemPrompt は SPEC §4② のシステムプロンプト。
const systemPrompt = `あなたはIT技術と文学に精通した小説家です。
渡された GitHub リポジトリの情報（ディレクトリ構成、README、主要ソースコード、
コミット履歴）からプロジェクトの目的・構造・歩みを解釈し、それらをメタファーとして
用いた魅力的なショートショート（500文字程度）を作成してください。`

// BuildUserRequest は SPEC §4② の User Request テンプレートを組み立てる。
func BuildUserRequest(m model.Material) string {
	return fmt.Sprintf(`・ディレクトリツリー:
%s
・README:
%s
・主要ソースコード:
%s
・コミット履歴:
%s
・世界観・スタイル指定:
%s`, m.DirectoryTree, m.Readme, m.SelectedFiles, m.CommitLog, m.CustomPrompt)
}

// ConverseAPI は Bedrock Converse 呼び出しの最小インターフェイス。
//
// 実 SDK クライアント（*bedrockruntime.Client）を差し替え可能にし、
// 単体テストで実 AWS へ接続せずに検証できるようにする。
type ConverseAPI interface {
	Converse(ctx context.Context, params *bedrockruntime.ConverseInput, optFns ...func(*bedrockruntime.Options)) (*bedrockruntime.ConverseOutput, error)
}

// Generator は Bedrock を用いてショートショートを生成する。
type Generator struct {
	api ConverseAPI
}

// NewGenerator は ConverseAPI 実装を注入して Generator を生成する。
func NewGenerator(api ConverseAPI) *Generator {
	return &Generator{api: api}
}

// Generate は model_id を検証の上で Converse API を呼び、生成結果を返す。
//
// model_id がホワイトリスト外の場合は API を呼ばず ErrModelNotAllowed を返す。
func (g *Generator) Generate(ctx context.Context, modelID string, m model.Material) (model.GenerationResult, error) {
	if err := ValidateModelID(modelID); err != nil {
		return model.GenerationResult{}, err
	}

	out, err := g.api.Converse(ctx, &bedrockruntime.ConverseInput{
		ModelId: aws.String(modelID),
		System: []brtypes.SystemContentBlock{
			&brtypes.SystemContentBlockMemberText{Value: systemPrompt},
		},
		Messages: []brtypes.Message{{
			Role: brtypes.ConversationRoleUser,
			Content: []brtypes.ContentBlock{
				&brtypes.ContentBlockMemberText{Value: BuildUserRequest(m)},
			},
		}},
		InferenceConfig: &brtypes.InferenceConfiguration{
			MaxTokens:   aws.Int32(MaxTokens),
			Temperature: aws.Float32(Temperature),
		},
	})
	if err != nil {
		return model.GenerationResult{}, fmt.Errorf("bedrock converse 呼び出しに失敗: %w", err)
	}

	story, err := extractText(out)
	if err != nil {
		return model.GenerationResult{}, err
	}
	return model.GenerationResult{
		Story: story,
		Usage: extractUsage(out),
	}, nil
}

// extractText は Converse 応答からアシスタントの生成テキストを取り出す。
func extractText(out *bedrockruntime.ConverseOutput) (string, error) {
	if out == nil {
		return "", ErrEmptyResponse
	}
	msg, ok := out.Output.(*brtypes.ConverseOutputMemberMessage)
	if !ok {
		return "", ErrEmptyResponse
	}
	for _, block := range msg.Value.Content {
		if text, ok := block.(*brtypes.ContentBlockMemberText); ok {
			return text.Value, nil
		}
	}
	return "", ErrEmptyResponse
}

// extractUsage は Converse 応答からトークン使用量を取り出す。
func extractUsage(out *bedrockruntime.ConverseOutput) model.Usage {
	if out == nil || out.Usage == nil {
		return model.Usage{}
	}
	return model.Usage{
		InputTokens:  aws.ToInt32(out.Usage.InputTokens),
		OutputTokens: aws.ToInt32(out.Usage.OutputTokens),
	}
}
