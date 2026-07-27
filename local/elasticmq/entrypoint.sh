#!/bin/sh
# elasticmq.conf をテンプレートから生成して ElasticMQ を起動する。
#
# HOCON の ${?ENV} 参照を使わないのは、elasticmq-native が GraalVM ネイティブ
# イメージで、実行時の環境変数を設定解決へ反映しないため（設定しても既定値のまま
# 起動してしまい、効いていないことに気づけない）。
set -eu

# 可視性タイムアウト。単位付きの HOCON duration で指定する（例: "180 seconds"）。
VISIBILITY_TIMEOUT="${LOCAL_QUEUE_VISIBILITY_TIMEOUT:-}"
if [ -z "$VISIBILITY_TIMEOUT" ]; then
  VISIBILITY_TIMEOUT="5 seconds"
fi

# 生成先を /tmp にするのは、ベースイメージが非 root ユーザーで動作し
# /opt へ書き込めないため。
RENDERED_CONFIG=/tmp/elasticmq.conf

sed "s|@@VISIBILITY_TIMEOUT@@|${VISIBILITY_TIMEOUT}|g" \
  /opt/elasticmq.conf.template > "$RENDERED_CONFIG"

echo "[elasticmq-entrypoint] defaultVisibilityTimeout = ${VISIBILITY_TIMEOUT}"

exec /opt/elasticmq/bin/elasticmq-native-server \
  -Dconfig.file="$RENDERED_CONFIG" \
  -Dlogback.configurationFile=/opt/logback.xml \
  "$@"
