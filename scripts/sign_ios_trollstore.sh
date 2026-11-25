#!/usr/bin/env bash
# 把 flutter build ios --release --no-codesign 产出的 Runner.app 伪签名并打成
# TrollStore 可安装的 IPA。TrollStore 会用假根证书重装并保留 ldid 写入的权限，
# 因此这里不需要 Apple 开发者账号，也不需要描述文件。
set -euo pipefail

APP="${1:-build/ios/iphoneos/Runner.app}"
OUT="${2:-dist/fqapp-ios-trollstore.ipa}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
ENTITLEMENTS="$APP_DIR/ios/entitlements/trollstore.plist"

if [ ! -d "$APP" ]; then
  echo "错误：找不到 App 包 $APP" >&2
  exit 1
fi
if [ ! -f "$ENTITLEMENTS" ]; then
  echo "错误：找不到 entitlements $ENTITLEMENTS" >&2
  exit 1
fi
if ! command -v ldid >/dev/null 2>&1; then
  echo "错误：未找到 ldid，请先执行 brew install ldid" >&2
  exit 1
fi
if ! command -v zip >/dev/null 2>&1; then
  echo "错误：未找到 zip" >&2
  exit 1
fi

MAIN="$APP/Runner"
if [ ! -f "$MAIN" ]; then
  echo "错误：$APP 中找不到主可执行文件 Runner" >&2
  exit 1
fi

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/fqapp-trollstore.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/Payload" "$(dirname "$OUT")"
cp -R "$APP" "$STAGE/Payload/Runner.app"

# 给包内所有 Mach-O（主程序、动态库、framework）逐个伪签名；ldid 必须
# 签实际文件而不是符号链接，所以这里用 -type f。
signed=0
while IFS= read -r -d '' file; do
  if file -b "$file" | grep -q 'Mach-O'; then
    ldid -S"$ENTITLEMENTS" "$file"
    signed=$((signed + 1))
  fi
done < <(find "$STAGE/Payload/Runner.app" -type f -print0)

if [ "$signed" -lt 1 ]; then
  echo "错误：没有找到任何 Mach-O 文件，签名失败" >&2
  exit 1
fi

# 校验伪签名确实写进了主二进制，且 entitlements 可读。
ldid -e "$STAGE/Payload/Runner.app/Runner" >/dev/null
echo "==> 已伪签名 $signed 个 Mach-O 文件"

OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
(cd "$STAGE" && zip -qry "$OUT_ABS" Payload)

# IPA 完整性 + 签名回读验证。
unzip -tq "$OUT_ABS" >/dev/null
ldid -e "$STAGE/Payload/Runner.app/Runner" >/dev/null
shasum -a 256 "$OUT_ABS" | awk '{print $1}' > "$OUT_ABS.sha256"
echo "==> 已生成：$OUT_ABS"
echo "==> SHA-256：$(cat "$OUT_ABS.sha256")"
