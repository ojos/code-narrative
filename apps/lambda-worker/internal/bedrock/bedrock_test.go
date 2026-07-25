package bedrock

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/bedrockruntime"
	brtypes "github.com/aws/aws-sdk-go-v2/service/bedrockruntime/types"

	"github.com/ojos/code-narrative/apps/lambda-worker/internal/model"
)

// fakeConverse は ConverseAPI のテスト用実装。
type fakeConverse struct {
	out    *bedrockruntime.ConverseOutput
	err    error
	called bool
	gotIn  *bedrockruntime.ConverseInput
}

func (f *fakeConverse) Converse(_ context.Context, in *bedrockruntime.ConverseInput, _ ...func(*bedrockruntime.Options)) (*bedrockruntime.ConverseOutput, error) {
	f.called = true
	f.gotIn = in
	return f.out, f.err
}

func TestValidateModelID(t *testing.T) {
	for _, id := range []string{
		"jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
		"amazon.nova-lite-v1:0",
	} {
		if err := ValidateModelID(id); err != nil {
			t.Errorf("許可モデル %q が拒否された: %v", id, err)
		}
	}

	// 東京(ap-northeast-1)で無効な旧 ID(us. プロファイル / Llama)は拒否される。
	for _, id := range []string{
		"evil.model:1",
		"us.anthropic.claude-sonnet-4-5-20250929-v1:0",
		"us.meta.llama3-3-70b-instruct-v1:0",
	} {
		if err := ValidateModelID(id); !errors.Is(err, ErrModelNotAllowed) {
			t.Errorf("非許可モデル %q で ErrModelNotAllowed を期待したが: %v", id, err)
		}
	}
}

func TestGenerate_Success(t *testing.T) {
	fake := &fakeConverse{
		out: &bedrockruntime.ConverseOutput{
			Output: &brtypes.ConverseOutputMemberMessage{Value: brtypes.Message{
				Role:    brtypes.ConversationRoleAssistant,
				Content: []brtypes.ContentBlock{&brtypes.ContentBlockMemberText{Value: "生成された物語"}},
			}},
			Usage: &brtypes.TokenUsage{
				InputTokens:  aws.Int32(123),
				OutputTokens: aws.Int32(45),
			},
		},
	}
	g := NewGenerator(fake)

	res, err := g.Generate(context.Background(), "amazon.nova-lite-v1:0", model.Material{DirectoryTree: "a.go"})
	if err != nil {
		t.Fatalf("想定外エラー: %v", err)
	}
	if res.Story != "生成された物語" {
		t.Errorf("story = %q", res.Story)
	}
	if res.Usage.InputTokens != 123 || res.Usage.OutputTokens != 45 {
		t.Errorf("usage = %+v", res.Usage)
	}

	// 既定パラメータが渡っていることを確認。
	if aws.ToInt32(fake.gotIn.InferenceConfig.MaxTokens) != MaxTokens {
		t.Errorf("MaxTokens = %d", aws.ToInt32(fake.gotIn.InferenceConfig.MaxTokens))
	}
	if aws.ToFloat32(fake.gotIn.InferenceConfig.Temperature) != Temperature {
		t.Errorf("Temperature = %f", aws.ToFloat32(fake.gotIn.InferenceConfig.Temperature))
	}
	if aws.ToString(fake.gotIn.ModelId) != "amazon.nova-lite-v1:0" {
		t.Errorf("ModelId = %q", aws.ToString(fake.gotIn.ModelId))
	}
}

func TestGenerate_ModelNotAllowed_SkipsAPI(t *testing.T) {
	fake := &fakeConverse{}
	g := NewGenerator(fake)

	_, err := g.Generate(context.Background(), "bad.model", model.Material{})
	if !errors.Is(err, ErrModelNotAllowed) {
		t.Fatalf("ErrModelNotAllowed を期待したが: %v", err)
	}
	if fake.called {
		t.Error("非許可モデルで Converse API が呼ばれてはならない")
	}
}

func TestGenerate_APIError(t *testing.T) {
	fake := &fakeConverse{err: errors.New("throttled")}
	g := NewGenerator(fake)

	_, err := g.Generate(context.Background(), "amazon.nova-lite-v1:0", model.Material{})
	if err == nil {
		t.Fatal("API エラーが伝播すべき")
	}
}

func TestBuildUserRequest_ContainsSections(t *testing.T) {
	m := model.Material{
		DirectoryTree: "main.go",
		Readme:        "README本文",
		SelectedFiles: "package main",
		CommitLog:     "- 初回",
		CustomPrompt:  "サイバーパンク風",
	}
	got := BuildUserRequest(m)
	for _, want := range []string{"main.go", "README本文", "package main", "- 初回", "サイバーパンク風", "ディレクトリツリー", "世界観・スタイル指定"} {
		if !strings.Contains(got, want) {
			t.Errorf("User Request に %q が含まれない", want)
		}
	}
}
