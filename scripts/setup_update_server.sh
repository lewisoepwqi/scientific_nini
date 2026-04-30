#!/usr/bin/env bash
# 交互式配置 Nini 应用内更新静态服务器。
# 用法：SSH 登录服务器后执行 `bash setup_update_server.sh`。

set -Eeuo pipefail

SERVICE_NAME="nini-updates"
DEFAULT_ROOT="/opt/nini-updates/public"
DEFAULT_CHANNEL="stable"
DEFAULT_BIND_HOST="0.0.0.0"
DEFAULT_PORT="8080"
DEFAULT_EXAMPLE_VERSION="0.1.2"

info() {
  printf '\033[1;34m[INFO]\033[0m %s\n' "$*"
}

warn() {
  printf '\033[1;33m[WARN]\033[0m %s\n' "$*"
}

fail() {
  printf '\033[1;31m[FAIL]\033[0m %s\n' "$*" >&2
  exit 1
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令：$1"
}

run_as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
    return
  fi
  need_command sudo
  sudo "$@"
}

write_root_file() {
  local target="$1"
  local content="$2"
  if [[ "$(id -u)" -eq 0 ]]; then
    printf '%s' "$content" >"$target"
    return
  fi
  need_command sudo
  printf '%s' "$content" | sudo tee "$target" >/dev/null
}

prompt_default() {
  local prompt="$1"
  local default="$2"
  local value
  read -r -p "$prompt [$default]: " value
  printf '%s' "${value:-$default}"
}

prompt_yes_no() {
  local prompt="$1"
  local default="${2:-Y}"
  local answer
  local hint="[Y/n]"
  if [[ "$default" =~ ^[Nn]$ ]]; then
    hint="[y/N]"
  fi

  while true; do
    read -r -p "$prompt $hint: " answer
    answer="${answer:-$default}"
    case "$answer" in
      y|Y|yes|YES) return 0 ;;
      n|N|no|NO) return 1 ;;
      *) warn "请输入 y 或 n" ;;
    esac
  done
}

detect_server_ip() {
  local ip=""
  if command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  if [[ -z "$ip" ]]; then
    ip="服务器IP"
  fi
  printf '%s' "$ip"
}

validate_no_spaces() {
  local name="$1"
  local value="$2"
  [[ "$value" != *" "* ]] || fail "$name 暂不支持包含空格：$value"
}

validate_port() {
  local port="$1"
  [[ "$port" =~ ^[0-9]+$ ]] || fail "端口必须是数字：$port"
  (( port >= 1 && port <= 65535 )) || fail "端口超出范围：$port"
}

create_directories() {
  local root="$1"
  local channel="$2"
  local current_user
  local current_group

  current_user="$(id -un)"
  current_group="$(id -gn)"

  run_as_root mkdir -p "$root/nini/updates/$channel"
  run_as_root mkdir -p "$root/nini/updates/beta"
  run_as_root chmod -R a+rX "$root"

  if [[ "$(id -u)" -ne 0 ]]; then
    run_as_root chown -R "$current_user:$current_group" "$root"
  fi
}

write_readme() {
  local root="$1"
  local channel="$2"
  local base_url="$3"
  local example_version="$4"
  local upload_file="$root/nini/updates/UPLOAD_INSTRUCTIONS.txt"
  cat >"$upload_file" <<EOF
Nini 更新服务器目录已创建。

当前渠道目录：
  $root/nini/updates/$channel

客户端配置：
  NINI_UPDATE_BASE_URL=$base_url/nini/updates/
  NINI_UPDATE_CHANNEL=$channel

如果使用 HTTP 内网地址，还需要：
  NINI_UPDATE_ALLOW_INSECURE_HTTP=true

从本地电脑上传发布文件示例：
  scp dist/latest.json 用户名@服务器IP:$root/nini/updates/$channel/latest.json
  scp dist/Nini-$example_version-Setup.exe 用户名@服务器IP:$root/nini/updates/$channel/Nini-$example_version-Setup.exe
  scp dist/Nini-$example_version-Setup.exe.sha256 用户名@服务器IP:$root/nini/updates/$channel/Nini-$example_version-Setup.exe.sha256

浏览器检查：
  $base_url/nini/updates/$channel/latest.json
EOF
}

install_systemd_service() {
  local root="$1"
  local bind_host="$2"
  local port="$3"
  local python_bin="$4"
  local unit_path="/etc/systemd/system/$SERVICE_NAME.service"
  local user_line=""

  if [[ "$(id -u)" -ne 0 ]]; then
    user_line="User=$(id -un)
Group=$(id -gn)"
  fi

  local unit
  unit="[Unit]
Description=Nini update static file server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
$user_line
WorkingDirectory=$root
ExecStart=$python_bin -m http.server $port --bind $bind_host --directory $root
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"

  write_root_file "$unit_path" "$unit"
  run_as_root systemctl daemon-reload
  run_as_root systemctl enable --now "$SERVICE_NAME.service"
}

configure_firewall() {
  local port="$1"
  if command -v ufw >/dev/null 2>&1; then
    run_as_root ufw allow "$port/tcp"
    return
  fi
  if command -v firewall-cmd >/dev/null 2>&1; then
    run_as_root firewall-cmd --add-port="$port/tcp" --permanent
    run_as_root firewall-cmd --reload
    return
  fi
  warn "未检测到 ufw 或 firewalld，请在云服务器安全组/防火墙中手动放行 TCP $port"
}

main() {
  [[ "$(uname -s)" != MINGW* && "$(uname -s)" != CYGWIN* ]] || fail "请在 Linux 服务器上运行此脚本"
  need_command awk

  local python_bin
  python_bin="$(command -v python3 || true)"
  [[ -n "$python_bin" ]] || fail "服务器需要安装 python3"

  echo "=== Nini 更新服务器交互式配置 ==="
  echo
  info "此脚本会创建静态文件目录，并可配置后台服务。"
  info "服务器只负责托管 latest.json 和 Nini 安装包，不运行 Nini 后端。"
  echo

  local root
  local channel
  local bind_host
  local port
  local detected_ip
  local public_host
  local example_version
  local scheme
  local base_url

  root="$(prompt_default "发布文件根目录" "$DEFAULT_ROOT")"
  channel="$(prompt_default "更新渠道" "$DEFAULT_CHANNEL")"
  bind_host="$(prompt_default "监听地址" "$DEFAULT_BIND_HOST")"
  port="$(prompt_default "监听端口" "$DEFAULT_PORT")"
  detected_ip="$(detect_server_ip)"
  public_host="$(prompt_default "客户端访问的服务器 IP 或主机名" "$detected_ip")"
  example_version="$(prompt_default "上传示例使用的 Nini 版本号" "$DEFAULT_EXAMPLE_VERSION")"

  if prompt_yes_no "客户端是否通过 HTTPS 访问" "N"; then
    scheme="https"
  else
    scheme="http"
  fi

  validate_no_spaces "发布文件根目录" "$root"
  validate_no_spaces "更新渠道" "$channel"
  validate_no_spaces "监听地址" "$bind_host"
  validate_port "$port"

  base_url="$scheme://$public_host:$port"

  echo
  info "准备创建目录：$root/nini/updates/$channel"
  create_directories "$root" "$channel"
  write_readme "$root" "$channel" "$base_url" "$example_version"

  echo
  if command -v systemctl >/dev/null 2>&1 && prompt_yes_no "是否创建 systemd 后台服务" "Y"; then
    install_systemd_service "$root" "$bind_host" "$port" "$python_bin"
    info "后台服务已启动：$SERVICE_NAME.service"
  else
    warn "未创建后台服务。你可以手动运行："
    echo "  $python_bin -m http.server $port --bind $bind_host --directory $root"
  fi

  echo
  if prompt_yes_no "是否尝试放行服务器本机防火墙端口 $port" "Y"; then
    configure_firewall "$port"
  else
    warn "请确认云服务器安全组和系统防火墙已放行 TCP $port"
  fi

  echo
  echo "=== 配置完成 ==="
  echo
  echo "服务器目录："
  echo "  $root/nini/updates/$channel"
  echo
  echo "浏览器测试地址："
  echo "  $base_url/nini/updates/$channel/latest.json"
  echo
  echo "Nini 客户端 .env 配置："
  echo "  NINI_UPDATE_BASE_URL=$base_url/nini/updates/"
  echo "  NINI_UPDATE_CHANNEL=$channel"
  if [[ "$scheme" == "http" ]]; then
    echo "  NINI_UPDATE_ALLOW_INSECURE_HTTP=true"
  fi
  echo
  echo "从本地电脑上传文件示例："
  echo "  scp dist/latest.json 用户名@$public_host:$root/nini/updates/$channel/latest.json"
  echo "  scp dist/Nini-$example_version-Setup.exe 用户名@$public_host:$root/nini/updates/$channel/Nini-$example_version-Setup.exe"
  echo
  echo "如果 latest.json 还不存在，浏览器测试地址返回 404 是正常的；上传后再检查即可。"
}

main "$@"
