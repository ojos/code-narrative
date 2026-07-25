# ECR リポジトリ(単一)。API / Worker / Stats それぞれのイメージ用に本モジュールを
# 複数回呼び出す。Lambda(コンテナイメージ)は本リポジトリの URI を参照するため、
# Lambda よりも先に作成されている必要がある(初回 apply の順序については
# environments/prod の README / コメントを参照)。

resource "aws_ecr_repository" "this" {
  name                 = var.repository_name
  image_tag_mutability = var.image_tag_mutability
  force_delete         = var.force_delete

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# 未タグイメージを一定日数で失効させ、レジストリの肥大化とコストを抑える。
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_expire_days
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
