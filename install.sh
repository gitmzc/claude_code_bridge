#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_PREFIX="${CODEX_INSTALL_PREFIX:-$HOME/.local/share/codex-dual}"
BIN_DIR="${CODEX_BIN_DIR:-$HOME/.local/bin}"
readonly REPO_ROOT INSTALL_PREFIX BIN_DIR

# i18n support
detect_lang() {
  local lang="${CCB_LANG:-auto}"
  case "$lang" in
    zh|cn|chinese) echo "zh" ;;
    en|english) echo "en" ;;
    *)
      local sys_lang="${LANG:-${LC_ALL:-${LC_MESSAGES:-}}}"
      if [[ "$sys_lang" == zh* ]] || [[ "$sys_lang" == *chinese* ]]; then
        echo "zh"
      else
        echo "en"
      fi
      ;;
  esac
}

CCB_LANG_DETECTED="$(detect_lang)"

# Message function
msg() {
  local key="$1"
  shift
  local en_msg zh_msg
  case "$key" in
    install_complete)
      en_msg="Installation complete"
      zh_msg="安装完成" ;;
    uninstall_complete)
      en_msg="Uninstall complete"
      zh_msg="卸载完成" ;;
    python_version_old)
      en_msg="Python version too old: $1"
      zh_msg="Python 版本过旧: $1" ;;
    requires_python)
      en_msg="Requires Python 3.10+"
      zh_msg="需要 Python 3.10+" ;;
    missing_dep)
      en_msg="Missing dependency: $1"
      zh_msg="缺少依赖: $1" ;;
    detected_env)
      en_msg="Detected $1 environment"
      zh_msg="检测到 $1 环境" ;;
    wsl1_not_supported)
      en_msg="WSL 1 does not support FIFO pipes, please upgrade to WSL 2"
      zh_msg="WSL 1 不支持 FIFO 管道，请升级到 WSL 2" ;;
    confirm_wsl)
      en_msg="Confirm continue installing in WSL? (y/N)"
      zh_msg="确认继续在 WSL 中安装？(y/N)" ;;
    cancelled)
      en_msg="Installation cancelled"
      zh_msg="安装已取消" ;;
    wsl_warning)
      en_msg="Detected WSL environment"
      zh_msg="检测到 WSL 环境" ;;
    same_env_required)
      en_msg="ccb/cask-w must run in the same environment as codex/gemini."
      zh_msg="ccb/cask-w 必须与 codex/gemini 在同一环境运行。" ;;
    confirm_wsl_native)
      en_msg="Please confirm: you will install and run codex/gemini in WSL (not Windows native)."
      zh_msg="请确认：你将在 WSL 中安装并运行 codex/gemini（不是 Windows 原生）。" ;;
    wezterm_recommended)
      en_msg="Recommend installing WezTerm as terminal frontend"
      zh_msg="推荐安装 WezTerm 作为终端前端" ;;
    *)
      en_msg="$key"
      zh_msg="$key" ;;
  esac
  if [[ "$CCB_LANG_DETECTED" == "zh" ]]; then
    echo "$zh_msg"
  else
    echo "$en_msg"
  fi
}

SCRIPTS_TO_LINK=(
  bin/cask
  bin/cask-w
  bin/cpend
  bin/cping
  bin/gask
  bin/gask-w
  bin/gpend
  bin/gping
  bin/ccb-ask
  ccb
)

CLAUDE_MARKDOWN=(
  cask.md
  cask-w.md
  cpend.md
  cping.md
  gask.md
  gask-w.md
  gpend.md
  gping.md
)

LEGACY_SCRIPTS=(
  cast
  cast-w
  codex-ask
  codex-pending
  codex-ping
  claude-codex-dual
  claude_codex
  claude_ai
  claude_bridge
)

usage() {
  cat <<'USAGE'
Usage:
  ./install.sh install    # Install or update Codex dual-window tools
  ./install.sh uninstall  # Uninstall installed content

Optional environment variables:
  CODEX_INSTALL_PREFIX     Install directory (default: ~/.local/share/codex-dual)
  CODEX_BIN_DIR            Executable directory (default: ~/.local/bin)
  CODEX_CLAUDE_COMMAND_DIR Custom Claude commands directory (default: auto-detect)
USAGE
}

detect_claude_dir() {
  if [[ -n "${CODEX_CLAUDE_COMMAND_DIR:-}" ]]; then
    echo "$CODEX_CLAUDE_COMMAND_DIR"
    return
  fi

  local candidates=(
    "$HOME/.claude/commands"
    "$HOME/.config/claude/commands"
    "$HOME/.local/share/claude/commands"
  )

  for dir in "${candidates[@]}"; do
    if [[ -d "$dir" ]]; then
      echo "$dir"
      return
    fi
  done

  local fallback="$HOME/.claude/commands"
  mkdir -p "$fallback"
  echo "$fallback"
}

require_command() {
  local cmd="$1"
  local pkg="${2:-$1}"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "❌ Missing dependency: $cmd"
    echo "   Please install $pkg first, then re-run install.sh"
    exit 1
  fi
}

require_python_version() {
  # ccb requires Python 3.10+ (PEP 604 type unions: `str | None`, etc.)
  local version
  version="$(python3 -c 'import sys; print("{}.{}.{}".format(sys.version_info[0], sys.version_info[1], sys.version_info[2]))' 2>/dev/null || echo unknown)"
  if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "❌ Python version too old: $version"
    echo "   Requires Python 3.10+, please upgrade and retry"
    exit 1
  fi
  echo "✓ Python $version"
}

# Return linux / macos / unknown based on uname
detect_platform() {
  local name
  name="$(uname -s 2>/dev/null || echo unknown)"
  case "$name" in
    Linux) echo "linux" ;;
    Darwin) echo "macos" ;;
    *) echo "unknown" ;;
  esac
}

is_wsl() {
  [[ -f /proc/version ]] && grep -qi microsoft /proc/version 2>/dev/null
}

get_wsl_version() {
  if [[ -n "${WSL_INTEROP:-}" ]]; then
    echo 2
  else
    echo 1
  fi
}

check_wsl_compatibility() {
  if is_wsl; then
    local ver
    ver="$(get_wsl_version)"
    if [[ "$ver" == "1" ]]; then
      echo "❌ WSL 1 does not support FIFO pipes, please upgrade to WSL 2"
      echo "   Run: wsl --set-version <distro> 2"
      exit 1
    fi
    echo "✅ Detected WSL 2 environment"
  fi
}

confirm_backend_env_wsl() {
  if ! is_wsl; then
    return
  fi

  if [[ "${CCB_INSTALL_ASSUME_YES:-}" == "1" ]]; then
    return
  fi

  if [[ ! -t 0 ]]; then
    echo "❌ Installing in WSL but detected non-interactive terminal; aborted to avoid env mismatch."
    echo "   If you confirm codex/gemini will be installed and run in WSL:"
    echo "   Re-run: CCB_INSTALL_ASSUME_YES=1 ./install.sh install"
    exit 1
  fi

  echo
  echo "================================================================"
  echo "⚠️  Detected WSL environment"
  echo "================================================================"
  echo "ccb/cask-w must run in the same environment as codex/gemini."
  echo
  echo "Please confirm: you will install and run codex/gemini in WSL (not Windows native)."
  echo "If you plan to run codex/gemini in Windows native, exit and run on Windows side:"
  echo "   powershell -ExecutionPolicy Bypass -File .\\install.ps1 install"
  echo "================================================================"
  echo
  read -r -p "Confirm continue installing in WSL? (y/N): " reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "Installation cancelled"; exit 1 ;;
  esac
}

# Detect if running in iTerm2 environment
is_iterm2_environment() {
  # Check ITERM_SESSION_ID environment variable
  if [[ -n "${ITERM_SESSION_ID:-}" ]]; then
    return 0
  fi
  # Check TERM_PROGRAM
  if [[ "${TERM_PROGRAM:-}" == "iTerm.app" ]]; then
    return 0
  fi
  # Check if iTerm2 is running on macOS
  if [[ "$(uname)" == "Darwin" ]] && pgrep -x "iTerm2" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

# Install it2 CLI
install_it2() {
  echo
  echo "📦 Installing it2 CLI..."

  # Check if pip3 is available
  if ! command -v pip3 >/dev/null 2>&1; then
    echo "❌ pip3 not found, cannot auto-install it2"
    echo "   Please run manually: python3 -m pip install it2"
    return 1
  fi

  # Install it2
  if pip3 install it2 --user 2>&1; then
    echo "✅ it2 CLI installed successfully"

    # Check if in PATH
    if ! command -v it2 >/dev/null 2>&1; then
      local user_bin
      user_bin="$(python3 -m site --user-base)/bin"
      echo
      echo "⚠️ it2 may not be in PATH, please add the following to your shell config:"
      echo "   export PATH=\"$user_bin:\$PATH\""
    fi
    return 0
  else
    echo "❌ it2 installation failed"
    return 1
  fi
}

# Show iTerm2 Python API enable reminder
show_iterm2_api_reminder() {
  echo
  echo "================================================================"
  echo "🔔 Important: Please enable Python API in iTerm2"
  echo "================================================================"
  echo "   Steps:"
  echo "   1. Open iTerm2"
  echo "   2. Go to Preferences (⌘ + ,)"
  echo "   3. Select Magic tab"
  echo "   4. Check \"Enable Python API\""
  echo "   5. Confirm the warning dialog"
  echo "================================================================"
  echo
}

require_terminal_backend() {
  local wezterm_override="${CODEX_WEZTERM_BIN:-${WEZTERM_BIN:-}}"

  # ============================================
  # Prioritize detecting current environment
  # ============================================

  # 1. If running in WezTerm environment
  if [[ -n "${WEZTERM_PANE:-}" ]]; then
    if [[ -n "${wezterm_override}" ]] && { command -v "${wezterm_override}" >/dev/null 2>&1 || [[ -f "${wezterm_override}" ]]; }; then
      echo "✓ Detected WezTerm environment (${wezterm_override})"
      return
    fi
    if command -v wezterm >/dev/null 2>&1 || command -v wezterm.exe >/dev/null 2>&1; then
      echo "✓ Detected WezTerm environment"
      return
    fi
  fi

  # 2. If running in iTerm2 environment
  if is_iterm2_environment; then
    # Check if it2 is installed
    if command -v it2 >/dev/null 2>&1; then
      echo "✓ Detected iTerm2 environment (it2 CLI installed)"
      echo "   💡 Please ensure iTerm2 Python API is enabled (Preferences > Magic > Enable Python API)"
      return
    fi

    # it2 not installed, ask to install
    echo "🍎 Detected iTerm2 environment but it2 CLI not installed"
    echo
    read -p "Auto-install it2 CLI? (Y/n): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
      if install_it2; then
        show_iterm2_api_reminder
        return
      fi
    else
      echo "Skipping it2 installation"
    fi
  fi

  # ============================================
  # Not in specific environment, detect by availability
  # ============================================

  # 3. Check WezTerm environment variable override
  if [[ -n "${wezterm_override}" ]]; then
    if command -v "${wezterm_override}" >/dev/null 2>&1 || [[ -f "${wezterm_override}" ]]; then
      echo "✓ Detected WezTerm (${wezterm_override})"
      return
    fi
  fi

  # 4. Check WezTerm command
  if command -v wezterm >/dev/null 2>&1 || command -v wezterm.exe >/dev/null 2>&1; then
    echo "✓ Detected WezTerm"
    return
  fi

  # WSL: Windows PATH may not be injected, try common install paths
  if [[ -f "/proc/version" ]] && grep -qi microsoft /proc/version 2>/dev/null; then
    if [[ -x "/mnt/c/Program Files/WezTerm/wezterm.exe" ]] || [[ -f "/mnt/c/Program Files/WezTerm/wezterm.exe" ]]; then
      echo "✓ Detected WezTerm (/mnt/c/Program Files/WezTerm/wezterm.exe)"
      return
    fi
    if [[ -x "/mnt/c/Program Files (x86)/WezTerm/wezterm.exe" ]] || [[ -f "/mnt/c/Program Files (x86)/WezTerm/wezterm.exe" ]]; then
      echo "✓ Detected WezTerm (/mnt/c/Program Files (x86)/WezTerm/wezterm.exe)"
      return
    fi
  fi

  # 5. Check it2 CLI
  if command -v it2 >/dev/null 2>&1; then
    echo "✓ Detected it2 CLI"
    return
  fi

  # 6. No terminal multiplexer found
  echo "❌ Missing dependency: WezTerm or it2 (at least one required)"
  echo "   WezTerm website: https://wezfurlong.org/wezterm/"

  # Extra hint for macOS users about iTerm2 + it2
  if [[ "$(uname)" == "Darwin" ]]; then
    echo
    echo "💡 macOS user recommended options:"
    echo "   - If using iTerm2, install it2 CLI: pip3 install it2"
    echo "   - Or install WezTerm: brew install --cask wezterm"
  fi

  exit 1
}

has_wezterm() {
  local wezterm_override="${CODEX_WEZTERM_BIN:-${WEZTERM_BIN:-}}"
  if [[ -n "${wezterm_override}" ]]; then
    command -v "${wezterm_override}" >/dev/null 2>&1 || [[ -f "${wezterm_override}" ]] && return 0
  fi
  command -v wezterm >/dev/null 2>&1 && return 0
  command -v wezterm.exe >/dev/null 2>&1 && return 0
  if [[ -f "/proc/version" ]] && grep -qi microsoft /proc/version 2>/dev/null; then
    [[ -f "/mnt/c/Program Files/WezTerm/wezterm.exe" ]] && return 0
    [[ -f "/mnt/c/Program Files (x86)/WezTerm/wezterm.exe" ]] && return 0
  fi
  return 1
}

detect_wezterm_path() {
  local wezterm_override="${CODEX_WEZTERM_BIN:-${WEZTERM_BIN:-}}"
  if [[ -n "${wezterm_override}" ]] && [[ -f "${wezterm_override}" ]]; then
    echo "${wezterm_override}"
    return
  fi
  local found
  found="$(command -v wezterm 2>/dev/null)" && [[ -n "$found" ]] && echo "$found" && return
  found="$(command -v wezterm.exe 2>/dev/null)" && [[ -n "$found" ]] && echo "$found" && return
  if is_wsl; then
    for drive in c d e f; do
      for path in "/mnt/${drive}/Program Files/WezTerm/wezterm.exe" \
                  "/mnt/${drive}/Program Files (x86)/WezTerm/wezterm.exe"; do
        if [[ -f "$path" ]]; then
          echo "$path"
          return
        fi
      done
    done
  fi
}

save_wezterm_config() {
  local wezterm_path
  wezterm_path="$(detect_wezterm_path)"
  if [[ -n "$wezterm_path" ]]; then
    mkdir -p "$HOME/.config/ccb"
    echo "CODEX_WEZTERM_BIN=${wezterm_path}" > "$HOME/.config/ccb/env"
    echo "✓ WezTerm path cached: $wezterm_path"
  fi
}

copy_project() {
  local staging
  staging="$(mktemp -d)"
  trap 'rm -rf "$staging"' EXIT

  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude '.git/' \
      --exclude '__pycache__/' \
      --exclude '.pytest_cache/' \
      --exclude '.mypy_cache/' \
      --exclude '.venv/' \
      "$REPO_ROOT"/ "$staging"/
  else
    tar -C "$REPO_ROOT" \
      --exclude '.git' \
      --exclude '__pycache__' \
      --exclude '.pytest_cache' \
      --exclude '.mypy_cache' \
      --exclude '.venv' \
      -cf - . | tar -C "$staging" -xf -
  fi

  rm -rf "$INSTALL_PREFIX"
  mkdir -p "$(dirname "$INSTALL_PREFIX")"
  mv "$staging" "$INSTALL_PREFIX"
  trap - EXIT

  # Update GIT_COMMIT and GIT_DATE in ccb file
  local git_commit="" git_date=""

  # Method 1: From git repo
  if command -v git >/dev/null 2>&1 && [[ -d "$REPO_ROOT/.git" ]]; then
    git_commit=$(git -C "$REPO_ROOT" log -1 --format='%h' 2>/dev/null || echo "")
    git_date=$(git -C "$REPO_ROOT" log -1 --format='%cs' 2>/dev/null || echo "")
  fi

  # Method 2: From environment variables (set by ccb update)
  if [[ -z "$git_commit" && -n "${CCB_GIT_COMMIT:-}" ]]; then
    git_commit="$CCB_GIT_COMMIT"
    git_date="${CCB_GIT_DATE:-}"
  fi

  # Method 3: From GitHub API (fallback)
  if [[ -z "$git_commit" ]] && command -v curl >/dev/null 2>&1; then
    local api_response
    api_response=$(curl -fsSL "https://api.github.com/repos/bfly123/claude_code_bridge/commits/main" 2>/dev/null || echo "")
    if [[ -n "$api_response" ]]; then
      git_commit=$(echo "$api_response" | grep -o '"sha": "[^"]*"' | head -1 | cut -d'"' -f4 | cut -c1-7)
      git_date=$(echo "$api_response" | grep -o '"date": "[^"]*"' | head -1 | cut -d'"' -f4 | cut -c1-10)
    fi
  fi

  if [[ -n "$git_commit" && -f "$INSTALL_PREFIX/ccb" ]]; then
    sed -i.bak "s/^GIT_COMMIT = .*/GIT_COMMIT = \"$git_commit\"/" "$INSTALL_PREFIX/ccb"
    sed -i.bak "s/^GIT_DATE = .*/GIT_DATE = \"$git_date\"/" "$INSTALL_PREFIX/ccb"
    rm -f "$INSTALL_PREFIX/ccb.bak"
  fi
}

install_bin_links() {
  mkdir -p "$BIN_DIR"

  for path in "${SCRIPTS_TO_LINK[@]}"; do
    local name
    name="$(basename "$path")"
    if [[ ! -f "$INSTALL_PREFIX/$path" ]]; then
      echo "⚠️ Script not found $INSTALL_PREFIX/$path, skipping link creation"
      continue
    fi
    chmod +x "$INSTALL_PREFIX/$path"
    if ln -sf "$INSTALL_PREFIX/$path" "$BIN_DIR/$name" 2>/dev/null; then
      :
    else
      # Windows (Git Bash) / restricted environments may not allow symlinks. Fall back to copying.
      cp -f "$INSTALL_PREFIX/$path" "$BIN_DIR/$name"
      chmod +x "$BIN_DIR/$name" 2>/dev/null || true
    fi
  done

  for legacy in "${LEGACY_SCRIPTS[@]}"; do
    rm -f "$BIN_DIR/$legacy"
  done

  echo "Created executable links in $BIN_DIR"
}

install_claude_commands() {
  local claude_dir
  claude_dir="$(detect_claude_dir)"
  mkdir -p "$claude_dir"

  for doc in "${CLAUDE_MARKDOWN[@]}"; do
    cp -f "$REPO_ROOT/commands/$doc" "$claude_dir/$doc"
    chmod 0644 "$claude_dir/$doc" 2>/dev/null || true
  done

  echo "Updated Claude commands directory: $claude_dir"
}

CCB_START_MARKER="<!-- CCB_CONFIG_START -->"
CCB_END_MARKER="<!-- CCB_CONFIG_END -->"
LEGACY_RULE_MARKER="## Codex 协作规则"

remove_codex_mcp() {
  local claude_config="$HOME/.claude.json"

  if [[ ! -f "$claude_config" ]]; then
    return
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "⚠️ python3 required to detect MCP configuration"
    return
  fi

  local has_codex_mcp
  has_codex_mcp=$(python3 -c "
import json
try:
    with open('$claude_config', 'r') as f:
        data = json.load(f)
    found = False
    for proj, cfg in data.get('projects', {}).items():
        servers = cfg.get('mcpServers', {})
        for name in list(servers.keys()):
            if 'codex' in name.lower():
                found = True
                break
        if found:
            break
    print('yes' if found else 'no')
except:
    print('no')
" 2>/dev/null)

  if [[ "$has_codex_mcp" == "yes" ]]; then
    echo "⚠️ Detected codex-related MCP configuration, removing to avoid conflicts..."
    python3 -c "
import json
with open('$claude_config', 'r') as f:
    data = json.load(f)
removed = []
for proj, cfg in data.get('projects', {}).items():
    servers = cfg.get('mcpServers', {})
    for name in list(servers.keys()):
        if 'codex' in name.lower():
            del servers[name]
            removed.append(f'{proj}: {name}')
with open('$claude_config', 'w') as f:
    json.dump(data, f, indent=2)
if removed:
    print('Removed the following MCP configurations:')
    for r in removed:
        print(f'  - {r}')
"
    echo "✅ Codex MCP configuration cleaned"
  fi
}

install_claude_md_config() {
  local claude_md="$HOME/.claude/CLAUDE.md"
  mkdir -p "$HOME/.claude"

  # Use temp file to avoid Bash 3.2 heredoc parsing bug with single quotes
  local ccb_tmpfile=""
  ccb_tmpfile="$(mktemp)" || { echo "Failed to create temp file"; return 1; }
  trap 'rm -f "${ccb_tmpfile:-}"' RETURN
  cat > "$ccb_tmpfile" << 'AI_RULES'
<!-- CCB_CONFIG_START -->
## OpenSpec 多 AI 协作规则

当使用 OpenSpec 工作流时，Claude Code 作为主协调者，可以委派任务给 Codex 和 Gemini。

### 任务分配策略
- **Gemini**: 前端任务（React/Vue/CSS/UI组件/样式等）
- **Codex**: 后端任务（API/数据库/服务端逻辑/CLI等）
- **Claude**: 协调整体流程、整合反馈、全栈任务

### 协作场景
- **规范审查**: 让多个 AI 审查 proposal.md 或 spec.md
- **任务分配**: 将 tasks.md 中的任务按前后端分配给对应 AI
- **设计讨论**: 在 design.md 决策时征求多方意见

---

## Codex Collaboration Rules
Codex is another AI assistant running in a separate terminal session (WezTerm or iTerm2). When user intent involves asking/consulting/collaborating with Codex:

**CRITICAL: 必须同步执行 cask-w，禁止使用 run_in_background=true**

Fast path (minimize latency):
- If the user message starts with any of: `@codex`, `codex:`, `codex：`, `ask codex`, `let codex`, `问codex`, `让codex`, `调取codex`, `/cask-w` then immediately run:
  - `Bash(cask-w "<message>")` (同步执行，等待完成)
- If user message is only the prefix (no content), ask a 1-line clarification for what to send.

Trigger conditions (any match):
- User mentions codex/Codex with questioning/requesting tone
- User wants codex to do something, give advice, or help review
- User asks about codex's status or previous reply

Command selection (always use Bash wrapper):
- 需要立即结果 -> `Bash(cask-w "<question>")` (同步阻塞直到回复)
- 长时间任务/不需要等待 -> `Bash(cask "<question>")` (fire and forget)
- 检查连接状态 -> `Bash(cping)`
- 查看之前的回复 -> `Bash(cpend)`
- 查看最近 N 轮对话 -> `Bash(cpend N)`
- 如果 cask-w 超时，使用 `Bash(cpend)` 检查延迟的回复

Context awareness (重要):
- Codex 在独立终端运行，看不到你当前的上下文
- 发送问题时必须包含相关文件路径和代码片段
- 错误示例: `cask-w "重构这个函数"`
- 正确示例: `cask-w "重构 lib/utils.py 中的 process_data 函数:\n<代码片段>"`

Examples:
- "what does codex think" / "问codex怎么看" -> `Bash(cask-w "...")`
- "ask codex to review this" -> `Bash(cask-w "请审查 src/main.py 中的这段代码:\n<粘贴代码>")`
- "is codex alive" / "codex在吗" -> `Bash(cping)`
- "don't wait for reply" / "不用等回复" -> `Bash(cask "...")`
- "view codex reply" / "看codex回复" -> `Bash(cpend)`

---

## Gemini Collaboration Rules
Gemini is another AI assistant running in a separate terminal session (WezTerm or iTerm2). When user intent involves asking/consulting/collaborating with Gemini:

**CRITICAL: 必须同步执行 gask-w，禁止使用 run_in_background=true**

**注意: Gemini 可能会分多条消息回复，需要多次检查 gpend 直到回复完整**

Fast path (minimize latency):
- If the user message starts with any of: `@gemini`, `gemini:`, `gemini：`, `ask gemini`, `let gemini`, `问gemini`, `让gemini`, `调取gemini`, `/gask-w` then immediately run:
  - `Bash(gask-w "<message>")` (同步执行，等待完成)
- If user message is only the prefix (no content), ask a 1-line clarification for what to send.

Trigger conditions (any match):
- User mentions gemini/Gemini with questioning/requesting tone
- User wants gemini to do something, give advice, or help review
- User asks about gemini's status or previous reply

Command selection (always use Bash wrapper):
- 需要立即结果 -> `Bash(gask-w "<question>")` (同步阻塞直到回复)
- 长时间任务/不需要等待 -> `Bash(gask "<question>")` (fire and forget)
- 检查连接状态 -> `Bash(gping)`
- 查看之前的回复 -> `Bash(gpend)`
- 查看最近 N 轮对话 -> `Bash(gpend N)`
- 如果 gask-w 超时，使用 `Bash(gpend)` 检查延迟的回复

Context awareness (重要):
- Gemini 在独立终端运行，看不到你当前的上下文
- 发送问题时必须包含相关文件路径和代码片段
- 错误示例: `gask-w "解释一下这个"`
- 正确示例: `gask-w "解释 src/auth.ts 中的认证流程:\n<代码片段>"`

Examples:
- "what does gemini think" / "问gemini怎么看" -> `Bash(gask-w "...")`
- "ask gemini to review this" -> `Bash(gask-w "请审查 src/main.py 中的这段代码:\n<粘贴代码>")`
- "is gemini alive" / "gemini在吗" -> `Bash(gping)`
- "don't wait for reply" / "不用等回复" -> `Bash(gask "...")`
- "view gemini reply" / "看gemini回复" -> `Bash(gpend)`

---

## 多 AI 并行协作

当需要多个 AI 同时工作时（如 "让 codex 和 gemini 一起审查"）：
- 方案1 (异步): 并行执行 `Bash(cask "...")` 和 `Bash(gask "...")`，然后用 `Bash(cpend)`/`Bash(gpend)` 查看结果
- 方案2 (同步顺序): 先执行 `Bash(cask-w "...")`，再执行 `Bash(gask-w "...")`，汇总两者结果
- 禁止对 cask-w/gask-w 使用 run_in_background=true

---

## Serena 项目记忆

当发现重要的项目知识时，使用 Serena MCP 工具记录：
- `write_memory`: 写入项目记忆（架构决策、约定、注意事项）
- `read_memory`: 读取项目记忆
- `list_memories`: 列出所有记忆

触发时机：
- 发现重要的架构决策或设计模式
- 用户明确说明的项目约定
- 踩坑经验或注意事项
- 跨会话需要记住的信息

首次使用时需激活项目：说 "Activate the current project using serena"
<!-- CCB_CONFIG_END -->
AI_RULES
  local ccb_content
  ccb_content="$(cat "$ccb_tmpfile")"

  if [[ -f "$claude_md" ]]; then
    if grep -q "$CCB_START_MARKER" "$claude_md" 2>/dev/null; then
      echo "Updating existing CCB config block..."
      python3 -c "
import re
with open('$claude_md', 'r', encoding='utf-8') as f:
    content = f.read()
pattern = r'<!-- CCB_CONFIG_START -->.*?<!-- CCB_CONFIG_END -->'
new_block = '''$ccb_content'''
content = re.sub(pattern, new_block, content, flags=re.DOTALL)
with open('$claude_md', 'w', encoding='utf-8') as f:
    f.write(content)
"
    elif grep -qE "$LEGACY_RULE_MARKER|## Codex Collaboration Rules|## Gemini" "$claude_md" 2>/dev/null; then
      echo "Removing legacy rules and adding new CCB config block..."
      python3 -c "
import re
with open('$claude_md', 'r', encoding='utf-8') as f:
    content = f.read()
patterns = [
    r'## Codex Collaboration Rules.*?(?=\n## (?!Gemini)|\Z)',
    r'## Codex 协作规则.*?(?=\n## |\Z)',
    r'## Gemini Collaboration Rules.*?(?=\n## |\Z)',
    r'## Gemini 协作规则.*?(?=\n## |\Z)',
]
for p in patterns:
    content = re.sub(p, '', content, flags=re.DOTALL)
content = content.rstrip() + '\n'
with open('$claude_md', 'w', encoding='utf-8') as f:
    f.write(content)
"
      echo "$ccb_content" >> "$claude_md"
    else
      echo "$ccb_content" >> "$claude_md"
    fi
  else
    echo "$ccb_content" > "$claude_md"
  fi

  echo "Updated AI collaboration rules in $claude_md"
}

install_codex_agents_config() {
  local codex_dir="$HOME/.codex"
  local agents_md="$codex_dir/AGENTS.md"
  mkdir -p "$codex_dir"

  local codex_tmpfile=""
  codex_tmpfile="$(mktemp)" || { echo "Failed to create temp file"; return 1; }
  trap 'rm -f "${codex_tmpfile:-}"' RETURN
  cat > "$codex_tmpfile" << 'CODEX_RULES'
### Claude Code Bridge 协作规则

当你通过 claude_code_bridge 被调用时，请遵循以下规则：

**代码修改限制（必须遵守）**

- 禁止擅自修改代码，必须先向用户说明修改方案并获得确认
- 只能进行分析、建议、审查等只读操作
- 如需修改代码，必须明确列出修改内容并等待用户批准
- 未经确认直接修改代码是严重违规行为

**回复结束标记（必须遵守）**

每次回复完成后，你必须在最后一行输出以下标记：

```
[CCB_REPLY_END]
```

这个标记用于让 claude_code_bridge 准确判断你的回复已经完成。

**注意事项：**
- 标记必须单独占一行
- 标记必须在回复的最末尾
- 不要在回复中间输出这个标记
- 即使是简短的回复也要输出这个标记

---

### CCB 命令使用规范（协作时必须遵守）

当你需要与其他 AI（如 Claude 或 Gemini）协作时：

**与 Gemini 协作：**
- 同步等待回复 -> `gask-w "<question>"` (阻塞直到收到回复)
- 只发送不等待 -> `gask "<question>"` (fire and forget)
- 检查连接状态 -> `gping`
- 查看之前的回复 -> `gpend`
- 查看最近 N 轮对话 -> `gpend N`

**重要：**
- `gask-w` 必须同步执行，不使用后台模式
- 回复必须以 `[CCB_REPLY_END]` 结尾，且只出现一次

---

### 语言规范

- 使用中文回复
- 代码注释使用中文

### 输出风格

- 简洁明了，直击重点
- 适当使用 emoji 增强可读性
- 代码块使用正确的语言标识

---

### Serena 项目记忆

当发现重要的项目知识时，使用 Serena MCP 工具记录：
- `write_memory`: 写入项目记忆（架构决策、约定、注意事项）
- `read_memory`: 读取项目记忆
- `list_memories`: 列出所有记忆

触发时机：
- 发现重要的架构决策或设计模式
- 用户明确说明的项目约定
- 踩坑经验或注意事项
- 跨会话需要记住的信息

首次使用时需激活项目：说 "Activate the current dir as project using serena"
CODEX_RULES

  cp -f "$codex_tmpfile" "$agents_md"
  echo "Updated Codex collaboration rules in $agents_md"
}

install_gemini_config() {
  local gemini_dir="$HOME/.gemini"
  local gemini_md="$gemini_dir/GEMINI.md"
  mkdir -p "$gemini_dir"

  local gemini_tmpfile=""
  gemini_tmpfile="$(mktemp)" || { echo "Failed to create temp file"; return 1; }
  trap 'rm -f "${gemini_tmpfile:-}"' RETURN
  cat > "$gemini_tmpfile" << 'GEMINI_RULES'
### Claude Code Bridge 协作规则

当你通过 claude_code_bridge 被调用时，请遵循以下规则：

**代码修改限制（必须遵守）**

- 禁止擅自修改代码，必须先向用户说明修改方案并获得确认
- 只能进行分析、建议、审查等只读操作
- 如需修改代码，必须明确列出修改内容并等待用户批准
- 未经确认直接修改代码是严重违规行为

**回复结束标记（必须遵守）**

每次回复完成后，你必须在最后一行输出以下标记：

```
[CCB_REPLY_END]
```

这个标记用于让 claude_code_bridge 准确判断你的回复已经完成。

**注意事项：**
- 标记必须单独占一行
- 标记必须在回复的最末尾
- 不要在回复中间输出这个标记
- 即使是简短的回复也要输出这个标记

---

### CCB 命令使用规范（协作时必须遵守）

当你需要与其他 AI（如 Claude 或 Codex）协作时：

**与 Codex 协作：**
- 同步等待回复 -> `cask-w "<question>"` (阻塞直到收到回复)
- 只发送不等待 -> `cask "<question>"` (fire and forget)
- 检查连接状态 -> `cping`
- 查看之前的回复 -> `cpend`
- 查看最近 N 轮对话 -> `cpend N`

**重要：**
- `cask-w` 必须同步执行，不使用后台模式
- 回复必须以 `[CCB_REPLY_END]` 结尾，且只出现一次

---

### 语言规范

- 使用中文回复
- 代码注释使用中文

### 输出风格

- 简洁明了，直击重点
- 适当使用 emoji 增强可读性
- 代码块使用正确的语言标识

---

### Serena 项目记忆

当发现重要的项目知识时，使用 Serena MCP 工具记录：
- `write_memory`: 写入项目记忆（架构决策、约定、注意事项）
- `read_memory`: 读取项目记忆
- `list_memories`: 列出所有记忆

触发时机：
- 发现重要的架构决策或设计模式
- 用户明确说明的项目约定
- 踩坑经验或注意事项
- 跨会话需要记住的信息

首次使用时需激活项目：说 "Activate the current project using serena"
GEMINI_RULES

  cp -f "$gemini_tmpfile" "$gemini_md"
  echo "Updated Gemini collaboration rules in $gemini_md"
}

# ============================================
# Serena MCP Server Configuration
# ============================================

check_uv_installed() {
  if command -v uvx >/dev/null 2>&1; then
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

install_serena_claude_code() {
  if ! check_uv_installed; then
    echo "⚠️ uvx not found, skipping Serena configuration for Claude Code"
    echo "   Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
    return 1
  fi

  if ! command -v claude >/dev/null 2>&1; then
    echo "⚠️ claude command not found, skipping Serena configuration for Claude Code"
    return 1
  fi

  if claude mcp add --scope user serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context=claude-code --project-from-cwd 2>/dev/null; then
    echo "✅ Serena MCP configured for Claude Code"
  else
    echo "⚠️ Failed to add Serena MCP to Claude Code (may already exist)"
  fi
}

install_serena_codex() {
  if ! check_uv_installed; then
    echo "⚠️ uvx not found, skipping Serena configuration for Codex"
    return 1
  fi

  local codex_config="$HOME/.codex/config.toml"
  mkdir -p "$HOME/.codex"

  if [[ -f "$codex_config" ]] && grep -q '\[mcp_servers.serena\]' "$codex_config" 2>/dev/null; then
    echo "✅ Serena MCP already configured for Codex"
    return 0
  fi

  if [[ -f "$codex_config" ]]; then
    cat >> "$codex_config" << 'SERENA_CODEX'

[mcp_servers.serena]
command = "uvx"
args = ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--context", "codex"]
SERENA_CODEX
  else
    cat > "$codex_config" << 'SERENA_CODEX'
[mcp_servers.serena]
command = "uvx"
args = ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--context", "codex"]
SERENA_CODEX
  fi
  echo "✅ Serena MCP configured for Codex"
}

install_serena_gemini() {
  if ! check_uv_installed; then
    echo "⚠️ uvx not found, skipping Serena configuration for Gemini"
    return 1
  fi

  local gemini_settings="$HOME/.gemini/settings.json"
  mkdir -p "$HOME/.gemini"

  if [[ ! -f "$gemini_settings" ]]; then
    cat > "$gemini_settings" << 'SERENA_GEMINI'
{
  "mcpServers": {
    "serena": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server", "--context", "ide"]
    }
  }
}
SERENA_GEMINI
    echo "✅ Serena MCP configured for Gemini"
    return 0
  fi

  if grep -q '"serena"' "$gemini_settings" 2>/dev/null; then
    echo "✅ Serena MCP already configured for Gemini"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 -c "
import json
with open('$gemini_settings', 'r') as f:
    data = json.load(f)
if 'mcpServers' not in data:
    data['mcpServers'] = {}
data['mcpServers']['serena'] = {
    'command': 'uvx',
    'args': ['--from', 'git+https://github.com/oraios/serena', 'serena', 'start-mcp-server', '--context', 'ide']
}
with open('$gemini_settings', 'w') as f:
    json.dump(data, f, indent=2)
"
    echo "✅ Serena MCP configured for Gemini"
  else
    echo "⚠️ python3 required to update Gemini settings"
    return 1
  fi
}

install_serena_all() {
  echo
  echo "📦 Configuring Serena MCP Server..."

  if ! check_uv_installed; then
    echo "⚠️ uv/uvx not found, skipping Serena configuration"
    echo "   To install uv: https://docs.astral.sh/uv/getting-started/installation/"
    return 1
  fi

  install_serena_claude_code
  install_serena_codex
  install_serena_gemini

  echo
  echo "📝 Serena usage notes:"
  echo "   - Claude Code: Serena auto-detects project from current directory"
  echo "   - Codex: Say 'Activate the current dir as project using serena'"
  echo "   - Gemini: Say 'Activate the current project using serena'"
  echo
}

uninstall_serena_all() {
  echo "🧹 Removing Serena MCP configuration..."

  if command -v claude >/dev/null 2>&1; then
    claude mcp remove --scope user serena 2>/dev/null && echo "Removed Serena from Claude Code" || true
  fi

  local codex_config="$HOME/.codex/config.toml"
  if [[ -f "$codex_config" ]] && grep -q '\[mcp_servers.serena\]' "$codex_config" 2>/dev/null; then
    if command -v python3 >/dev/null 2>&1; then
      python3 -c "
import re
with open('$codex_config', 'r') as f:
    content = f.read()
pattern = r'\n?\[mcp_servers\.serena\][^\[]*'
content = re.sub(pattern, '', content)
with open('$codex_config', 'w') as f:
    f.write(content.strip() + '\n')
"
      echo "Removed Serena from Codex"
    fi
  fi

  local gemini_settings="$HOME/.gemini/settings.json"
  if [[ -f "$gemini_settings" ]] && grep -q '"serena"' "$gemini_settings" 2>/dev/null; then
    if command -v python3 >/dev/null 2>&1; then
      python3 -c "
import json
with open('$gemini_settings', 'r') as f:
    data = json.load(f)
if 'mcpServers' in data and 'serena' in data['mcpServers']:
    del data['mcpServers']['serena']
with open('$gemini_settings', 'w') as f:
    json.dump(data, f, indent=2)
"
      echo "Removed Serena from Gemini"
    fi
  fi
}

install_settings_permissions() {
  local settings_file="$HOME/.claude/settings.json"
  mkdir -p "$HOME/.claude"

  local perms_to_add=(
    'Bash(cask:*)'
    'Bash(cask-w:*)'
    'Bash(cpend)'
    'Bash(cping)'
    'Bash(gask:*)'
    'Bash(gask-w:*)'
    'Bash(gpend)'
    'Bash(gping)'
  )

  if [[ ! -f "$settings_file" ]]; then
    cat > "$settings_file" << 'SETTINGS'
{
  "permissions": {
    "allow": [
      "Bash(cask:*)",
      "Bash(cask-w:*)",
      "Bash(cpend)",
      "Bash(cping)",
      "Bash(gask:*)",
      "Bash(gask-w:*)",
      "Bash(gpend)",
      "Bash(gping)"
    ],
    "deny": []
  }
}
SETTINGS
    echo "Created $settings_file with permissions"
    return
  fi

  local added=0
  for perm in "${perms_to_add[@]}"; do
    if ! grep -q "$perm" "$settings_file" 2>/dev/null; then
      if command -v python3 >/dev/null 2>&1; then
        python3 -c "
import json, sys
with open('$settings_file', 'r') as f:
    data = json.load(f)
if 'permissions' not in data:
    data['permissions'] = {'allow': [], 'deny': []}
if 'allow' not in data['permissions']:
    data['permissions']['allow'] = []
if '$perm' not in data['permissions']['allow']:
    data['permissions']['allow'].append('$perm')
with open('$settings_file', 'w') as f:
    json.dump(data, f, indent=2)
"
        added=1
      fi
    fi
  done

  if [[ $added -eq 1 ]]; then
    echo "Updated $settings_file permissions"
  else
    echo "Permissions already exist in $settings_file"
  fi
}

install_requirements() {
  check_wsl_compatibility
  confirm_backend_env_wsl
  require_command python3 python3
  require_python_version
  require_terminal_backend
  if ! has_wezterm; then
    echo
    echo "================================================================"
    echo "⚠️ Recommend installing WezTerm as terminal frontend (better experience, recommended for WSL2/Windows)"
    echo "   - Website: https://wezfurlong.org/wezterm/"
    echo "   - Benefits: Smoother split/scroll/font rendering, more stable bridging in WezTerm mode"
    echo "================================================================"
    echo
  fi
}

install_all() {
  install_requirements
  remove_codex_mcp
  save_wezterm_config
  copy_project
  install_bin_links
  install_claude_commands
  install_claude_md_config
  install_codex_agents_config
  install_gemini_config
  install_settings_permissions
  install_serena_all
  echo "✅ Installation complete"
  echo "   Project dir    : $INSTALL_PREFIX"
  echo "   Executable dir : $BIN_DIR"
  echo "   Claude commands updated"
  echo "   Global CLAUDE.md configured with AI collaboration rules"
  echo "   Global ~/.codex/AGENTS.md configured"
  echo "   Global ~/.gemini/GEMINI.md configured"
  echo "   Global settings.json permissions added"
}

uninstall_claude_md_config() {
  local claude_md="$HOME/.claude/CLAUDE.md"

  if [[ ! -f "$claude_md" ]]; then
    return
  fi

  if grep -q "$CCB_START_MARKER" "$claude_md" 2>/dev/null; then
    echo "Removing CCB config block from CLAUDE.md..."
    if command -v python3 >/dev/null 2>&1; then
      python3 -c "
import re
with open('$claude_md', 'r', encoding='utf-8') as f:
    content = f.read()
pattern = r'\n?<!-- CCB_CONFIG_START -->.*?<!-- CCB_CONFIG_END -->\n?'
content = re.sub(pattern, '\n', content, flags=re.DOTALL)
content = content.strip() + '\n'
with open('$claude_md', 'w', encoding='utf-8') as f:
    f.write(content)
"
      echo "Removed CCB config from CLAUDE.md"
    else
      echo "⚠️ python3 required to clean CLAUDE.md, please manually remove CCB_CONFIG block"
    fi
  elif grep -qE "$LEGACY_RULE_MARKER|## Codex Collaboration Rules|## Gemini" "$claude_md" 2>/dev/null; then
    echo "Removing legacy collaboration rules from CLAUDE.md..."
    if command -v python3 >/dev/null 2>&1; then
      python3 -c "
import re
with open('$claude_md', 'r', encoding='utf-8') as f:
    content = f.read()
patterns = [
    r'## Codex Collaboration Rules.*?(?=\n## (?!Gemini)|\Z)',
    r'## Codex 协作规则.*?(?=\n## |\Z)',
    r'## Gemini Collaboration Rules.*?(?=\n## |\Z)',
    r'## Gemini 协作规则.*?(?=\n## |\Z)',
]
for p in patterns:
    content = re.sub(p, '', content, flags=re.DOTALL)
content = content.rstrip() + '\n'
with open('$claude_md', 'w', encoding='utf-8') as f:
    f.write(content)
"
      echo "Removed collaboration rules from CLAUDE.md"
    else
      echo "⚠️ python3 required to clean CLAUDE.md, please manually remove collaboration rules"
    fi
  fi
}

uninstall_settings_permissions() {
  local settings_file="$HOME/.claude/settings.json"

  if [[ ! -f "$settings_file" ]]; then
    return
  fi

  local perms_to_remove=(
    'Bash(cask:*)'
    'Bash(cask-w:*)'
    'Bash(cpend)'
    'Bash(cping)'
    'Bash(gask:*)'
    'Bash(gask-w:*)'
    'Bash(gpend)'
    'Bash(gping)'
  )

  if command -v python3 >/dev/null 2>&1; then
    local has_perms=0
    for perm in "${perms_to_remove[@]}"; do
      if grep -q "$perm" "$settings_file" 2>/dev/null; then
        has_perms=1
        break
      fi
    done

    if [[ $has_perms -eq 1 ]]; then
      echo "Removing permission configuration from settings.json..."
      python3 -c "
import json
perms_to_remove = [
    'Bash(cask:*)',
    'Bash(cask-w:*)',
    'Bash(cpend)',
    'Bash(cping)',
    'Bash(gask:*)',
    'Bash(gask-w:*)',
    'Bash(gpend)',
    'Bash(gping)',
]
with open('$settings_file', 'r') as f:
    data = json.load(f)
if 'permissions' in data and 'allow' in data['permissions']:
    data['permissions']['allow'] = [
        p for p in data['permissions']['allow']
        if p not in perms_to_remove
    ]
with open('$settings_file', 'w') as f:
    json.dump(data, f, indent=2)
"
      echo "Removed permission configuration from settings.json"
    fi
  else
    echo "⚠️ python3 required to clean settings.json, please manually remove related permissions"
  fi
}

uninstall_all() {
  echo "🧹 Starting ccb uninstall..."

  # 1. Remove project directory
  if [[ -d "$INSTALL_PREFIX" ]]; then
    rm -rf "$INSTALL_PREFIX"
    echo "Removed project directory: $INSTALL_PREFIX"
  fi

  # 2. Remove bin links
  for path in "${SCRIPTS_TO_LINK[@]}"; do
    local name
    name="$(basename "$path")"
    if [[ -L "$BIN_DIR/$name" || -f "$BIN_DIR/$name" ]]; then
      rm -f "$BIN_DIR/$name"
    fi
  done
  for legacy in "${LEGACY_SCRIPTS[@]}"; do
    rm -f "$BIN_DIR/$legacy"
  done
  echo "Removed bin links: $BIN_DIR"

  # 3. Remove Claude command files (clean all possible locations)
  local cmd_dirs=(
    "$HOME/.claude/commands"
    "$HOME/.config/claude/commands"
    "$HOME/.local/share/claude/commands"
  )
  for dir in "${cmd_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
      for doc in "${CLAUDE_MARKDOWN[@]}"; do
        rm -f "$dir/$doc"
      done
      echo "Cleaned commands directory: $dir"
    fi
  done

  # 4. Remove collaboration rules from CLAUDE.md
  uninstall_claude_md_config

  # 5. Remove permission configuration from settings.json
  uninstall_settings_permissions

  # 6. Remove Serena MCP configuration
  uninstall_serena_all

  echo "✅ Uninstall complete"
  echo "   💡 Note: Dependencies (python3, wezterm, it2) were not removed"
}

main() {
  if [[ $# -ne 1 ]]; then
    usage
    exit 1
  fi

  case "$1" in
    install)
      install_all
      ;;
    uninstall)
      uninstall_all
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
