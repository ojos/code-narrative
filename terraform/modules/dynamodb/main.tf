# 変換ジョブ・集計レコードを保持するテーブル(SPEC §4③)。
# - オンデマンド課金(PAY_PER_REQUEST)
# - 保存時暗号化を有効化
# - ユーザー別ジョブ一覧のための GSI(user_id + created_at)

resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = var.gsi_name
    hash_key        = "user_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }
}
