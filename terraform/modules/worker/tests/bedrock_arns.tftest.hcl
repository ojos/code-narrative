# worker IAM が Bedrock 許可 ARN を正しく導出することの検証(#44)。
#
# 検証したいのは locals の分類ロジックであって AWS への疎通ではないため、
# provider をモックして認証情報なしで回す。CI の terraform plan は既存 5 モデルに
# 差分が出ないことしか見られない(global. のモデルをホワイトリストへ入れること自体は
# #44 の scope 外)ので、仮のモデル ID を入力に与えられる単体検証をここに置く。

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }

  # aws_iam_policy_document もモック対象になるため、json 属性に妥当な値を与える。
  # 既定のモック値は JSON として不正で、aws_iam_role.assume_role_policy の
  # 検証に落ちる。
  #
  # この結果、レンダリング済みポリシーの中身はここでは検証できない。本テストの
  # 対象は locals の ARN 導出(output.bedrock_resource_arns)であり、そこは
  # data source に依存しないため検証は成立する。ポリシー全体の妥当性は CI の
  # terraform plan が受け持つ。
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

variables {
  function_name       = "code-narrative-worker-test"
  image_uri           = "123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/worker:test"
  sqs_queue_arn       = "arn:aws:sqs:ap-northeast-1:123456789012:jobs"
  dynamodb_table_name = "jobs"
  dynamodb_table_arn  = "arn:aws:dynamodb:ap-northeast-1:123456789012:table/jobs"
  dynamodb_gsi_arn    = "arn:aws:dynamodb:ap-northeast-1:123456789012:table/jobs/index/gsi1"
  bedrock_model_ids   = []
}

# 現行ホワイトリスト(#37 で選定した 5 件)での導出結果を固定する。
# ここが変わると CI の terraform plan にも差分が出るため、意図しない変更の検知点になる。
run "current_whitelist" {
  command = plan

  variables {
    bedrock_model_ids = [
      "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
      "amazon.nova-lite-v1:0",
      "deepseek.v3.2",
      "qwen.qwen3-32b-v1:0",
      "google.gemma-3-12b-it",
    ]
  }

  assert {
    condition = output.bedrock_resource_arns == [
      "arn:aws:bedrock:*:123456789012:inference-profile/jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0",
      "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
      "arn:aws:bedrock:*::foundation-model/deepseek.v3.2",
      "arn:aws:bedrock:*::foundation-model/qwen.qwen3-32b-v1:0",
      "arn:aws:bedrock:*::foundation-model/google.gemma-3-12b-it",
    ]
    error_message = "現行ホワイトリストの導出 ARN が変化しました。terraform plan にも差分が出ます。"
  }
}

# #44 の本題。global. は地理スコープではないが推論プロファイルである。
run "global_prefix_is_inference_profile" {
  command = plan

  variables {
    bedrock_model_ids = [
      "global.anthropic.claude-opus-4-5-20251101-v1:0",
    ]
  }

  assert {
    condition = contains(
      output.bedrock_resource_arns,
      "arn:aws:bedrock:*:123456789012:inference-profile/global.anthropic.claude-opus-4-5-20251101-v1:0"
    )
    error_message = "global. のモデルに inference-profile ARN が生成されていません(Foundation Model と誤分類されています)。"
  }

  assert {
    condition = contains(
      output.bedrock_resource_arns,
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-opus-4-5-20251101-v1:0"
    )
    error_message = "global. プレフィックスが除去された foundation-model ARN が生成されていません。"
  }

  # 誤分類時に生成される「存在しない ARN」が混ざらないこと。
  assert {
    condition = !contains(
      output.bedrock_resource_arns,
      "arn:aws:bedrock:*::foundation-model/global.anthropic.claude-opus-4-5-20251101-v1:0"
    )
    error_message = "プレフィックス付きの foundation-model ARN が生成されています。この ARN は存在せず AccessDeniedException になります。"
  }

  assert {
    condition     = length(output.bedrock_resource_arns) == 2
    error_message = "推論プロファイル 1 件からは inference-profile と foundation-model の 2 ARN だけが生成されるべきです。"
  }
}

# 既存の地理スコープが退行していないこと。
run "geo_prefixes_still_inference_profiles" {
  command = plan

  variables {
    bedrock_model_ids = [
      "us.anthropic.claude-x-v1:0",
      "eu.anthropic.claude-x-v1:0",
      "apac.anthropic.claude-x-v1:0",
      "jp.anthropic.claude-x-v1:0",
      "global.anthropic.claude-x-v1:0",
    ]
  }

  # 5 件すべてが推論プロファイルとして扱われ、各々 2 ARN を生む。
  assert {
    condition     = length(output.bedrock_resource_arns) == 10
    error_message = "スコーププレフィックス付き 5 件が推論プロファイルとして扱われていません。"
  }

  # プレフィックスを剥がすと全て同一の Foundation Model に収束する。
  assert {
    condition = length(setsubtract(
      toset([for a in output.bedrock_resource_arns : a if startswith(a, "arn:aws:bedrock:*::foundation-model/")]),
      toset(["arn:aws:bedrock:*::foundation-model/anthropic.claude-x-v1:0"])
    )) == 0
    error_message = "プレフィックス除去後の foundation-model ARN が期待値と一致しません。"
  }
}

# プレフィックスなしは Foundation Model 直接指定のまま。
run "unprefixed_models_are_direct" {
  command = plan

  variables {
    bedrock_model_ids = [
      "amazon.nova-lite-v1:0",
      "deepseek.v3.2",
    ]
  }

  assert {
    condition = output.bedrock_resource_arns == [
      "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
      "arn:aws:bedrock:*::foundation-model/deepseek.v3.2",
    ]
    error_message = "プレフィックスなしのモデルが Foundation Model 直接指定になっていません。"
  }
}
