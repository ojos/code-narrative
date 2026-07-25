# 子アカウント内のサブドメイン用ホストゾーン。
# ここで生成される NS レコード(output name_servers)を親ゾーン ojos.jp 側に登録して委任する。
#
# 親ゾーン ojos.jp は「標準のさくらのDNS」(ns1/ns2.dns.ne.jp、会員メニュー管理)で運用中。
# このサービスは Terraform プロバイダ・公開 API が無いため、委任 NS レコードは
# さくら会員メニューのゾーン編集で手動登録する(apply 後、`terraform output name_servers` の4件)。
# ※ Terraform 対応があるのは別サービスの「さくらのクラウド DNS」のみ(ojos.jp は非該当)。

resource "aws_route53_zone" "subdomain" {
  name    = var.subdomain
  comment = "Delegated subdomain for code-narrative (managed by terraform)"
}
