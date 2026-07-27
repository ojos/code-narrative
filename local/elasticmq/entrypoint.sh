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

# 受理する形を「数値 + 空白 + 単位」に限定する。
#
# エスケープではなく検証にするのは、この値がそのまま sed の置換文字列になるため。
# "&" や "|" や "\" を含む値は置換を壊すが、そもそも HOCON の duration として
# 不正なので、静かに直すより起動を止めて原因を見せた方がよい。単位の打ち間違いも
# ここで落ちる（設定が効かないまま既定値で動き続ける事故を防ぐ）。
case "$VISIBILITY_TIMEOUT" in
  *[!0-9\ a-z]*|"")
    echo "[elasticmq-entrypoint] LOCAL_QUEUE_VISIBILITY_TIMEOUT が不正です: '${VISIBILITY_TIMEOUT}'" >&2
    echo "[elasticmq-entrypoint] 例: '5 seconds' / '180 seconds' / '3 minutes'" >&2
    exit 1
    ;;
esac
if ! echo "$VISIBILITY_TIMEOUT" | grep -Eq '^[0-9]+ (millis|milliseconds|s|seconds|m|minutes|h|hours)$'; then
  echo "[elasticmq-entrypoint] LOCAL_QUEUE_VISIBILITY_TIMEOUT が不正です: '${VISIBILITY_TIMEOUT}'" >&2
  echo "[elasticmq-entrypoint] 例: '5 seconds' / '180 seconds' / '3 minutes'" >&2
  exit 1
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
