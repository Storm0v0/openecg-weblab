#!/usr/bin/env bash
set -euo pipefail
# Managed by OpenECG demo deployment bundle.
if [[ ${EUID} -ne 0 ]]; then
  echo '请通过 sudo bash install.sh 运行。' >&2
  exit 1
fi
ecg_port="${1:-80}"
if ! [[ "$ecg_port" =~ ^[0-9]{1,5}$ ]] || (( 10#$ecg_port < 1 || 10#$ecg_port > 65535 )); then
  echo '请选择 1–65535 的空闲端口，例如 80 或 8080。' >&2
  exit 1
fi
ecg_port=$((10#$ecg_port))
ecg_capabilities=''
if (( ecg_port < 1024 )); then
  ecg_capabilities=$'AmbientCapabilities=CAP_NET_BIND_SERVICE\nCapabilityBoundingSet=CAP_NET_BIND_SERVICE'
fi
ecg_python=$(command -v python3 || true)
if [[ -z "$ecg_python" ]]; then
  echo '服务器未安装 Python 3，请先安装后重试。' >&2
  exit 1
fi
command -v systemctl >/dev/null || { echo '此脚本需要 systemd；也可直接运行 python3 server.py。' >&2; exit 1; }
ecg_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ecg_target=/opt/openecg-demo
ecg_unit=/etc/systemd/system/openecg-demo.service
ecg_marker='Managed by OpenECG demo deployment bundle.'
for ecg_name in index.html server.py; do
  [[ -f "$ecg_source/$ecg_name" ]] || { echo "缺少文件：$ecg_name" >&2; exit 1; }
done
if [[ -e "$ecg_target" && ! -f "$ecg_target/DEPLOYMENT_MARKER" ]]; then
  echo '/opt/openecg-demo 已存在且不属于本部署包，已停止以保护原内容。' >&2
  exit 1
fi
if [[ -f "$ecg_unit" ]] && ! grep -Fq "$ecg_marker" "$ecg_unit"; then
  echo '同名服务已存在且不属于本部署包，已停止。' >&2
  exit 1
fi
id nobody >/dev/null 2>&1 || { echo '缺少 nobody 低权限服务账户。' >&2; exit 1; }
if ! systemctl is-active --quiet openecg-demo || ! grep -Eq -- "--port ${ecg_port}([[:space:]]|$)" "$ecg_unit"; then
  "$ecg_python" - "$ecg_port" <<'PY'
import socket,sys
try:
    with socket.socket() as s:
        s.bind(('0.0.0.0', int(sys.argv[1])))
except OSError as exc:
    raise SystemExit(f'该端口不可用，请另选端口：{exc}')
PY
fi
install -d -m 755 "$ecg_target"
install -m 644 "$ecg_source/index.html" "$ecg_target/index.html"
install -m 644 "$ecg_source/server.py" "$ecg_target/server.py"
printf '%s\n' "$ecg_marker" > "$ecg_target/DEPLOYMENT_MARKER"
cat > "$ecg_unit" <<UNIT
# $ecg_marker
[Unit]
Description=OpenECG static demonstration
After=network.target

[Service]
Type=simple
User=nobody
$ecg_capabilities
WorkingDirectory=$ecg_target
ExecStart="$ecg_python" "$ecg_target/server.py" --host 0.0.0.0 --port $ecg_port
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now openecg-demo
systemctl restart openecg-demo
if ! "$ecg_python" - "$ecg_port" "$ecg_target/index.html" <<'PY'
import hashlib
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

expected = Path(sys.argv[2]).read_bytes()
expected_digest = hashlib.sha256(expected).digest()
base = f'http://127.0.0.1:{int(sys.argv[1])}'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
deadline = time.monotonic() + 5.0
last_error = '服务尚未就绪'

def fetch(path, limit):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('已达到本机验收等待上限')
    with opener.open(base + path, timeout=min(0.5, remaining)) as response:
        if response.status != 200:
            raise RuntimeError(f'{path} 返回 HTTP {response.status}')
        return response.read(limit)

while time.monotonic() < deadline:
    try:
        if fetch('/health', 4) != b'ok\n':
            raise RuntimeError('健康检查内容不符')
        actual = fetch('/', len(expected) + 1)
        if len(actual) != len(expected) or hashlib.sha256(actual).digest() != expected_digest:
            raise RuntimeError('服务首页与本次安装的 index.html 不一致')
        if time.monotonic() > deadline:
            raise TimeoutError('已达到本机验收等待上限')
        break
    except (OSError, urllib.error.URLError, RuntimeError) as exc:
        last_error = str(exc)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.15, remaining))
else:
    raise SystemExit(f'本机服务未在 5 秒内通过健康检查及首页 SHA-256 验收：{last_error}')
PY
then
  echo '服务验收失败，请执行 journalctl -u openecg-demo -n 30 --no-pager 查看原因。' >&2
  exit 1
fi
if ! systemctl is-active --quiet openecg-demo || ! grep -Eq -- "--port ${ecg_port}([[:space:]]|$)" "$ecg_unit"; then
  echo '服务未能启动，请执行 journalctl -u openecg-demo -n 30 --no-pager 查看原因。' >&2
  exit 1
fi
echo "本机服务已启动。请放通安全组和系统防火墙的 TCP $ecg_port 端口。"
echo "访问地址：http://你的弹性公网IP:$ecg_port/"
echo "本机检查：curl http://127.0.0.1:$ecg_port/health"
