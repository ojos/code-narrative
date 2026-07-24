# 子アカウント内のサブドメイン用ホストゾーン。
# ここで生成される NS レコードを親ゾーン ojos.jp 側に登録して委任する
# (親ゾーンの管理先は intake の P2 に依存。Route 53 外ならそちらで NS を登録)。

resource "aws_route53_zone" "subdomain" {
  name    = var.subdomain
  comment = "Delegated subdomain for code-narrative (managed by terraform)"
}
