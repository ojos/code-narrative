# --- GitHub Actions OIDC プロバイダー ---

data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]
}

locals {
  repo_sub_prefix = "repo:${var.github_owner}/${var.github_repo}"
}

# --- state バケットへのアクセスポリシー(plan/apply 共通) ---

data "aws_iam_policy_document" "tfstate_access" {
  statement {
    sid       = "ListStateBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.tfstate.arn]
  }
  statement {
    sid    = "ReadWriteState"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject", # S3 ネイティブロックの解放に必要
    ]
    resources = ["${aws_s3_bucket.tfstate.arn}/*"]
  }
}

resource "aws_iam_policy" "tfstate_access" {
  name   = "code-narrative-tfstate-access"
  policy = data.aws_iam_policy_document.tfstate_access.json
}

# --- plan 用ロール(PR ブランチから。読み取り専用 + state) ---

data "aws_iam_policy_document" "plan_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.repo_sub_prefix}:pull_request"]
    }
  }
}

resource "aws_iam_role" "terraform_plan" {
  name                 = "github-actions-terraform-plan"
  assume_role_policy   = data.aws_iam_policy_document.plan_assume.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.terraform_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "plan_state" {
  role       = aws_iam_role.terraform_plan.name
  policy_arn = aws_iam_policy.tfstate_access.arn
}

# --- apply 用ロール(main ブランチのみ。書き込み) ---
# Terraform apply は Lambda 実行ロール等の IAM リソースを作成するため広い権限が必要。
# repo + main ブランチ限定の信頼条件と、GitHub Environments の承認で保護する前提。
# 運用が固まったら AdministratorAccess を必要権限へ絞ること。

data "aws_iam_policy_document" "apply_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.repo_sub_prefix}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "terraform_apply" {
  name                 = "github-actions-terraform-apply"
  assume_role_policy   = data.aws_iam_policy_document.apply_assume.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "apply_admin" {
  role       = aws_iam_role.terraform_apply.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
