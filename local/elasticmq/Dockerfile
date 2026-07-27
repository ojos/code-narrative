# syntax=docker/dockerfile:1

# SQS 互換キュー（ElasticMQ）。設定ファイルはイメージへ焼き込む。
#
# bind mount を使わないのは、この devcontainer が docker-outside-of-docker
# 構成で、ホスト側の docker デーモンから見たパスとコンテナ内のパスが一致しない
# ため。COPY で焼き込めば、devcontainer 内からでも素のホストからでも同じ結果になる。
FROM softwaremill/elasticmq-native:1.6.11

COPY elasticmq.conf.template /opt/elasticmq.conf.template
COPY entrypoint.sh /usr/local/bin/elasticmq-entrypoint.sh

# 元の ENTRYPOINT（tini 経由でサーバを直接起動）の手前に、設定生成の一段を挟む。
ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/elasticmq-entrypoint.sh"]
