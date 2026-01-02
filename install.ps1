param(
  [Parameter(Position = 0)]
  [ValidateSet("install", "uninstall", "help")]
  [string]$Command = "help",
  [string]$InstallPrefix = "$env:LOCALAPPDATA\codex-dual",
  [switch]$Yes
)

# --- UTF-8 / BOM compatibility (Windows PowerShell 5.1) ---
# Keep this near the top so Chinese/emoji output is rendered correctly.
try {
  $script:utf8NoBom = [System.Text.UTF8Encoding]::new($false)
} catch {
  $script:utf8NoBom = [System.Text.Encoding]::UTF8
}
try { $OutputEncoding = $script:utf8NoBom } catch {}
try { [Console]::OutputEncoding = $script:utf8NoBom } catch {}
try { [Console]::InputEncoding = $script:utf8NoBom } catch {}
try { chcp 65001 | Out-Null } catch {}

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# i18n support
function Get-CCBLang {
  $lang = $env:CCB_LANG
  if ($lang -in @("zh", "cn", "chinese")) { return "zh" }
  if ($lang -in @("en", "english")) { return "en" }
  # Auto-detect from system
  try {
    $culture = (Get-Culture).Name
    if ($culture -like "zh*") { return "zh" }
  } catch {}
  return "en"
}

$script:CCBLang = Get-CCBLang

function Get-Msg {
  param([string]$Key, [string]$Arg1 = "", [string]$Arg2 = "")
  $msgs = @{
    "install_complete" = @{ en = "Installation complete"; zh = "安装完成" }
    "uninstall_complete" = @{ en = "Uninstall complete"; zh = "卸载完成" }
    "python_old" = @{ en = "Python version too old: $Arg1"; zh = "Python 版本过旧: $Arg1" }
    "requires_python" = @{ en = "ccb requires Python 3.10+"; zh = "ccb 需要 Python 3.10+" }
    "confirm_windows" = @{ en = "Continue installation in Windows? (y/N)"; zh = "确认继续在 Windows 中安装？(y/N)" }
    "cancelled" = @{ en = "Installation cancelled"; zh = "安装已取消" }
    "windows_warning" = @{ en = "You are installing ccb in native Windows environment"; zh = "你正在 Windows 原生环境安装 ccb" }
    "same_env" = @{ en = "ccb/cask-w must run in the same environment as codex/gemini."; zh = "ccb/cask-w 必须与 codex/gemini 在同一环境运行。" }
  }
  if ($msgs.ContainsKey($Key)) {
    return $msgs[$Key][$script:CCBLang]
  }
  return $Key
}

function Show-Usage {
  Write-Host "Usage:"
  Write-Host "  .\install.ps1 install    # Install or update"
  Write-Host "  .\install.ps1 uninstall  # Uninstall"
  Write-Host ""
  Write-Host "Options:"
  Write-Host "  -InstallPrefix <path>    # Custom install location (default: $env:LOCALAPPDATA\codex-dual)"
  Write-Host ""
  Write-Host "Requirements:"
  Write-Host "  - Python 3.10+"
}

function Find-Python {
  if (Get-Command py -ErrorAction SilentlyContinue) { return "py -3" }
  if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
  if (Get-Command python3 -ErrorAction SilentlyContinue) { return "python3" }
  return $null
}

function Require-Python310 {
  param([string]$PythonCmd)

  $parts = $PythonCmd -split " " | Where-Object { $_ }
  $exe = $parts[0]
  $args = @()
  if ($parts.Length -gt 1) {
    $args = $parts[1..($parts.Length - 1)]
  }

  try {
    $vinfo = & $exe @args -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro} {v.major} {v.minor}')"
    $parts = $vinfo.Trim() -split " "
    $version = $parts[0]
    $major = [int]$parts[1]
    $minor = [int]$parts[2]
  } catch {
    Write-Host "[ERROR] Failed to query Python version using: $PythonCmd"
    exit 1
  }

  if (($major -ne 3) -or ($minor -lt 10)) {
    Write-Host "[ERROR] Python version too old: $version"
    Write-Host "   ccb requires Python 3.10+"
    Write-Host "   Download: https://www.python.org/downloads/"
    exit 1
  }
  Write-Host "[OK] Python $version"
}

function Confirm-BackendEnv {
  if ($Yes -or $env:CCB_INSTALL_ASSUME_YES -eq "1") { return }

  if (-not [Environment]::UserInteractive) {
    Write-Host "[ERROR] Non-interactive environment detected, aborting to prevent Windows/WSL mismatch."
    Write-Host "   If codex/gemini will run in native Windows:"
    Write-Host "   Re-run: powershell -ExecutionPolicy Bypass -File .\install.ps1 install -Yes"
    exit 1
  }

  Write-Host ""
  Write-Host "================================================================"
  Write-Host "[WARNING] You are installing ccb in native Windows environment"
  Write-Host "================================================================"
  Write-Host "ccb/cask-w must run in the same environment as codex/gemini."
  Write-Host ""
  Write-Host "Please confirm: You will install and run codex/gemini in native Windows (not WSL)."
  Write-Host "If you plan to run codex/gemini in WSL, exit and run in WSL:"
  Write-Host "   ./install.sh install"
  Write-Host "================================================================"
  $reply = Read-Host "Continue installation in Windows? (y/N)"
  if ($reply.Trim().ToLower() -notin @("y", "yes")) {
    Write-Host "Installation cancelled"
    exit 1
  }
}

function Install-Native {
  Confirm-BackendEnv

  $binDir = Join-Path $InstallPrefix "bin"
  $pythonCmd = Find-Python

  if (-not $pythonCmd) {
    Write-Host "Python not found. Please install Python and add it to PATH."
    Write-Host "Download: https://www.python.org/downloads/"
    exit 1
  }

  Require-Python310 -PythonCmd $pythonCmd

  Write-Host "Installing ccb to $InstallPrefix ..."
  Write-Host "Using Python: $pythonCmd"

  if (-not (Test-Path $InstallPrefix)) {
    New-Item -ItemType Directory -Path $InstallPrefix -Force | Out-Null
  }
  if (-not (Test-Path $binDir)) {
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null
  }

  $items = @("ccb", "lib", "bin", "commands")
  foreach ($item in $items) {
    $src = Join-Path $repoRoot $item
    $dst = Join-Path $InstallPrefix $item
    if (Test-Path $src) {
      if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
      Copy-Item -Recurse -Force $src $dst
    }
  }

  function Fix-PythonShebang {
    param([string]$TargetPath)
    if (-not $TargetPath -or -not (Test-Path $TargetPath)) { return }
    try {
      $text = [System.IO.File]::ReadAllText($TargetPath, [System.Text.Encoding]::UTF8)
      if ($text -match '^\#\!/usr/bin/env python3') {
        $text = $text -replace '^\#\!/usr/bin/env python3', '#!/usr/bin/env python'
        [System.IO.File]::WriteAllText($TargetPath, $text, $script:utf8NoBom)
      }
    } catch {
      return
    }
  }

  $scripts = @("ccb", "cask", "cask-w", "cping", "cpend", "gask", "gask-w", "gping", "gpend")

  # In MSYS/Git-Bash, invoking the script file directly will honor the shebang.
  # Windows typically has `python` but not `python3`, so rewrite shebangs for compatibility.
  foreach ($script in $scripts) {
    if ($script -eq "ccb") {
      Fix-PythonShebang (Join-Path $InstallPrefix "ccb")
    } else {
      Fix-PythonShebang (Join-Path $InstallPrefix ("bin\\" + $script))
    }
  }

  foreach ($script in $scripts) {
    $batPath = Join-Path $binDir "$script.bat"
    $cmdPath = Join-Path $binDir "$script.cmd"
    if ($script -eq "ccb") {
      $relPath = "..\\ccb"
    } else {
      # Script is installed alongside the wrapper under $InstallPrefix\bin
      $relPath = $script
    }
    $wrapperContent = "@echo off`r`nset `"PYTHON=python`"`r`nwhere python >NUL 2>&1 || set `"PYTHON=py -3`"`r`n%PYTHON% `"%~dp0$relPath`" %*"
    [System.IO.File]::WriteAllText($batPath, $wrapperContent, $script:utf8NoBom)
    # .cmd wrapper for PowerShell/CMD users (and tools preferring .cmd over raw shebang scripts)
    [System.IO.File]::WriteAllText($cmdPath, $wrapperContent, $script:utf8NoBom)
  }

  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $pathList = if ($userPath) { $userPath -split ";" | Where-Object { $_ } } else { @() }
  $binDirLower = $binDir.ToLower()
  $alreadyInPath = $pathList | Where-Object { $_.ToLower() -eq $binDirLower }
  if (-not $alreadyInPath) {
    $newPath = ($pathList + $binDir) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added $binDir to user PATH"
  }

  Install-ClaudeConfig
  Install-CodexConfig
  Install-GeminiConfig

  Write-Host ""
  Write-Host "Installation complete!"
  Write-Host "Restart your terminal (WezTerm) for PATH changes to take effect."
  Write-Host ""
  Write-Host "Configured:"
  Write-Host "  - ~/.claude/CLAUDE.md (AI collaboration rules)"
  Write-Host "  - ~/.codex/AGENTS.md (Codex rules)"
  Write-Host "  - ~/.gemini/GEMINI.md (Gemini rules)"
  Write-Host ""
  Write-Host "Quick start:"
  Write-Host "  ccb up codex    # Start with Codex backend"
  Write-Host "  ccb up gemini   # Start with Gemini backend"
}

function Install-ClaudeConfig {
  $claudeDir = Join-Path $env:USERPROFILE ".claude"
  $commandsDir = Join-Path $claudeDir "commands"
  $claudeMd = Join-Path $claudeDir "CLAUDE.md"
  $settingsJson = Join-Path $claudeDir "settings.json"

  if (-not (Test-Path $claudeDir)) {
    New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null
  }
  if (-not (Test-Path $commandsDir)) {
    New-Item -ItemType Directory -Path $commandsDir -Force | Out-Null
  }

  $srcCommands = Join-Path $repoRoot "commands"
  if (Test-Path $srcCommands) {
    Get-ChildItem -Path $srcCommands -Filter "*.md" | ForEach-Object {
      Copy-Item -Force $_.FullName (Join-Path $commandsDir $_.Name)
    }
  }

  # Install skills
  $skillsDir = Join-Path $claudeDir "skills"
  $srcSkills = Join-Path $repoRoot "skills"
  if (Test-Path $srcSkills) {
    if (-not (Test-Path $skillsDir)) {
      New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
    }
    Get-ChildItem -Path $srcSkills -Directory | ForEach-Object {
      $destPath = Join-Path $skillsDir $_.Name
      if (Test-Path $destPath) { Remove-Item -Recurse -Force $destPath }
      Copy-Item -Recurse $_.FullName $destPath
      Write-Host "  Installed skill: $($_.Name)"
    }
    Write-Host "Updated Claude skills directory: $skillsDir"
  }

  $codexRules = @"

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

## Codex Collaboration Rules (cask-w/cask)

Codex is another AI assistant running in a separate terminal.

**Tool Selection Guide:**
- Use **cask-w** (synchronous) when you need the answer immediately to formulate your response
- Use **cask** (async) only for fire-and-forget tasks or notifications

**IMPORTANT RESTRICTIONS:**
- NEVER use cpend/cask-w unless user EXPLICITLY requests collaboration with Codex
- After cask (async), ONLY wait for bash-notification to get results
- Do NOT try to fetch results yourself

---

## Gemini Collaboration Rules (gask-w/gask)

Gemini is another AI assistant running in a separate terminal.

**Tool Selection Guide:**
- Use **gask-w** (synchronous) when you need the answer immediately to formulate your response
- Use **gask** (async) only for fire-and-forget tasks or notifications

**IMPORTANT RESTRICTIONS:**
- NEVER use gpend/gask-w unless user EXPLICITLY requests collaboration with Gemini
- After gask (async), ONLY wait for bash-notification to get results
- Do NOT try to fetch results yourself

---

## 多 AI 并行协作

当需要多个 AI 同时工作时（如 "让 codex 和 gemini 一起审查"）：
- 方案1 (异步): 并行执行 ``Bash(cask "...")`` 和 ``Bash(gask "...")``, 然后用 ``Bash(cpend)``/``Bash(gpend)`` 查看结果
- 方案2 (同步顺序): 先执行 ``Bash(cask-w "...")``, 再执行 ``Bash(gask-w "...")``, 汇总两者结果
- 禁止对 cask-w/gask-w 使用 run_in_background=true

---

## Serena 项目记忆

当发现重要的项目知识时，使用 Serena MCP 工具记录：
- ``write_memory``: 写入项目记忆（架构决策、约定、注意事项）
- ``read_memory``: 读取项目记忆
- ``list_memories``: 列出所有记忆

触发时机：
- 发现重要的架构决策或设计模式
- 用户明确说明的项目约定
- 踩坑经验或注意事项
- 跨会话需要记住的信息

首次使用时需激活项目：说 "Activate the current project using serena"
<!-- CCB_CONFIG_END -->
"@

  if (Test-Path $claudeMd) {
    $content = Get-Content -Raw $claudeMd
    if ($content -like "*CCB_CONFIG_START*") {
      # Update existing CCB config block
      Write-Host "Updating existing CCB config block in CLAUDE.md"
      $pattern = '(?s)<!-- CCB_CONFIG_START -->.*?<!-- CCB_CONFIG_END -->'
      $content = [regex]::Replace($content, $pattern, $codexRules.Trim())
      $content | Out-File -Encoding UTF8 -FilePath $claudeMd
    } elseif ($content -notlike "*Codex Collaboration Rules*") {
      Add-Content -Path $claudeMd -Value $codexRules
      Write-Host "Updated CLAUDE.md with collaboration rules"
    }
  } else {
    $codexRules | Out-File -Encoding UTF8 -FilePath $claudeMd
    Write-Host "Created CLAUDE.md with collaboration rules"
  }

  $allowList = @(
    "Bash(cask:*)", "Bash(cask-w:*)", "Bash(cpend)", "Bash(cping)",
    "Bash(gask:*)", "Bash(gask-w:*)", "Bash(gpend)", "Bash(gping)"
  )

  if (Test-Path $settingsJson) {
    try {
      $settings = Get-Content -Raw $settingsJson | ConvertFrom-Json
    } catch {
      $settings = @{}
    }
  } else {
    $settings = @{}
  }

  if (-not $settings.permissions) {
    $settings | Add-Member -NotePropertyName "permissions" -NotePropertyValue @{} -Force
  }
  if (-not $settings.permissions.allow) {
    $settings.permissions | Add-Member -NotePropertyName "allow" -NotePropertyValue @() -Force
  }

  $currentAllow = [System.Collections.ArrayList]@($settings.permissions.allow)
  $updated = $false
  foreach ($item in $allowList) {
    if ($currentAllow -notcontains $item) {
      $currentAllow.Add($item) | Out-Null
      $updated = $true
    }
  }

  if ($updated) {
    $settings.permissions.allow = $currentAllow.ToArray()
    $settings | ConvertTo-Json -Depth 10 | Out-File -Encoding UTF8 -FilePath $settingsJson
    Write-Host "Updated settings.json with permissions"
  }
}

function Install-CodexConfig {
  $codexDir = Join-Path $env:USERPROFILE ".codex"
  $agentsMd = Join-Path $codexDir "AGENTS.md"

  if (-not (Test-Path $codexDir)) {
    New-Item -ItemType Directory -Path $codexDir -Force | Out-Null
  }

  $codexAgentsRules = @"
### Claude Code Bridge 协作规则

当你通过 claude_code_bridge 被调用时，请遵循以下规则：

**代码修改限制（必须遵守）**

- 禁止擅自修改代码，必须先向用户说明修改方案并获得确认
- 只能进行分析、建议、审查等只读操作
- 如需修改代码，必须明确列出修改内容并等待用户批准
- 未经确认直接修改代码是严重违规行为

**回复结束标记（必须遵守）**

每次回复完成后，你必须在最后一行输出以下标记：

``````
[CCB_REPLY_END]
``````

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
- 同步等待回复 -> ``gask-w "<question>"`` (阻塞直到收到回复)
- 只发送不等待 -> ``gask "<question>"`` (fire and forget)
- 检查连接状态 -> ``gping``
- 查看之前的回复 -> ``gpend``
- 查看最近 N 轮对话 -> ``gpend N``

**重要：**
- ``gask-w`` 必须同步执行，不使用后台模式
- 回复必须以 ``[CCB_REPLY_END]`` 结尾，且只出现一次

---

### 语言规范

- 使用中文回复
- 代码注释使用中文

### 输出风格

- 简洁明了，直击重点
- 适当使用 emoji 增强可读性
- 代码块使用正确的语言标识
"@

  $codexAgentsRules | Out-File -Encoding UTF8 -FilePath $agentsMd
  Write-Host "Updated Codex collaboration rules in $agentsMd"
}

function Install-GeminiConfig {
  $geminiDir = Join-Path $env:USERPROFILE ".gemini"
  $geminiMd = Join-Path $geminiDir "GEMINI.md"

  if (-not (Test-Path $geminiDir)) {
    New-Item -ItemType Directory -Path $geminiDir -Force | Out-Null
  }

  $geminiRules = @"
### Claude Code Bridge 协作规则

当你通过 claude_code_bridge 被调用时，请遵循以下规则：

**代码修改限制（必须遵守）**

- 禁止擅自修改代码，必须先向用户说明修改方案并获得确认
- 只能进行分析、建议、审查等只读操作
- 如需修改代码，必须明确列出修改内容并等待用户批准
- 未经确认直接修改代码是严重违规行为

**回复结束标记（必须遵守）**

每次回复完成后，你必须在最后一行输出以下标记：

``````
[CCB_REPLY_END]
``````

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
- 同步等待回复 -> ``cask-w "<question>"`` (阻塞直到收到回复)
- 只发送不等待 -> ``cask "<question>"`` (fire and forget)
- 检查连接状态 -> ``cping``
- 查看之前的回复 -> ``cpend``
- 查看最近 N 轮对话 -> ``cpend N``

**重要：**
- ``cask-w`` 必须同步执行，不使用后台模式
- 回复必须以 ``[CCB_REPLY_END]`` 结尾，且只出现一次

---

### 语言规范

- 使用中文回复
- 代码注释使用中文

### 输出风格

- 简洁明了，直击重点
- 适当使用 emoji 增强可读性
- 代码块使用正确的语言标识
"@

  $geminiRules | Out-File -Encoding UTF8 -FilePath $geminiMd
  Write-Host "Updated Gemini collaboration rules in $geminiMd"
}

function Uninstall-Native {
  $binDir = Join-Path $InstallPrefix "bin"

  if (Test-Path $InstallPrefix) {
    Remove-Item -Recurse -Force $InstallPrefix
    Write-Host "Removed $InstallPrefix"
  }

  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($userPath) {
    $pathList = $userPath -split ";" | Where-Object { $_ }
    $binDirLower = $binDir.ToLower()
    $newPathList = $pathList | Where-Object { $_.ToLower() -ne $binDirLower }
    if ($newPathList.Count -ne $pathList.Count) {
      $newPath = $newPathList -join ";"
      [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
      Write-Host "Removed $binDir from user PATH"
    }
  }

  Write-Host "Uninstall complete."
}

if ($Command -eq "help") {
  Show-Usage
  exit 0
}

if ($Command -eq "install") {
  Install-Native
  exit 0
}

if ($Command -eq "uninstall") {
  Uninstall-Native
  exit 0
}
