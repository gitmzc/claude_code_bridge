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

  Write-Host ""
  Write-Host "Installation complete!"
  Write-Host "Restart your terminal (WezTerm) for PATH changes to take effect."
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

  $codexRules = @"

<!-- CCB_CONFIG_START -->
## Codex Collaboration Rules
Codex is another AI assistant running in a separate terminal session (WezTerm or iTerm2). When user intent involves asking/consulting/collaborating with Codex:

**CRITICAL: cask-w must run synchronously. Do NOT use run_in_background=true**

Fast path (minimize latency):
- If the user message starts with any of: ``@codex``, ``codex:``, ``ask codex``, ``let codex``, ``/cask-w`` then immediately run:
  - ``Bash(cask-w "<message>")`` (synchronous, wait for output)
- If user message is only the prefix (no content), ask a 1-line clarification for what to send.

Trigger conditions (any match):
- User mentions codex/Codex with questioning/requesting tone
- User wants codex to do something, give advice, or help review
- User asks about codex's status or previous reply

Command selection (always use Bash wrapper):
- Need immediate result -> ``Bash(cask-w "<question>")`` (synchronous, blocks until reply)
- Long-running task / no need to wait -> ``Bash(cask "<question>")`` (fire and forget)
- Check connectivity -> ``Bash(cping)``
- View previous reply -> ``Bash(cpend)``
- View recent N conversations -> ``Bash(cpend N)``
- If cask-w times out, use ``Bash(cpend)`` to check for delayed reply

Context awareness (IMPORTANT):
- Codex runs in a separate terminal and cannot see your current context
- Always include relevant file paths and code snippets in your message
- Bad: ``cask-w "Refactor this function"``
- Good: ``cask-w "Refactor the process_data function in lib/utils.py:\n<code_snippet>"``

Examples:
- "what does codex think" -> ``Bash(cask-w "...")``
- "ask codex to review this" -> ``Bash(cask-w "Please review this code in src/main.py:\n<paste_code>")``
- "is codex alive" -> ``Bash(cping)``
- "don't wait for reply" -> ``Bash(cask "...")``
- "view codex reply" -> ``Bash(cpend)``

## Gemini Collaboration Rules
Gemini is another AI assistant running in a separate terminal session (WezTerm or iTerm2). When user intent involves asking/consulting/collaborating with Gemini:

**CRITICAL: gask-w must run synchronously. Do NOT use run_in_background=true**

Fast path (minimize latency):
- If the user message starts with any of: ``@gemini``, ``gemini:``, ``ask gemini``, ``let gemini``, ``/gask-w`` then immediately run:
  - ``Bash(gask-w "<message>")`` (synchronous, wait for output)
- If user message is only the prefix (no content), ask a 1-line clarification for what to send.

Trigger conditions (any match):
- User mentions gemini/Gemini with questioning/requesting tone
- User wants gemini to do something, give advice, or help review
- User asks about gemini's status or previous reply

Command selection (always use Bash wrapper):
- Need immediate result -> ``Bash(gask-w "<question>")`` (synchronous, blocks until reply)
- Long-running task / no need to wait -> ``Bash(gask "<question>")`` (fire and forget)
- Check connectivity -> ``Bash(gping)``
- View previous reply -> ``Bash(gpend)``
- View recent N conversations -> ``Bash(gpend N)``
- If gask-w times out, use ``Bash(gpend)`` to check for delayed reply

Context awareness (IMPORTANT):
- Gemini runs in a separate terminal and cannot see your current context
- Always include relevant file paths and code snippets in your message
- Bad: ``gask-w "Explain this"``
- Good: ``gask-w "Explain the authentication flow in src/auth.ts:\n<code_snippet>"``

Examples:
- "what does gemini think" -> ``Bash(gask-w "...")``
- "ask gemini to review this" -> ``Bash(gask-w "Please review this code in src/main.py:\n<paste_code>")``
- "is gemini alive" -> ``Bash(gping)``
- "don't wait for reply" -> ``Bash(gask "...")``
- "view gemini reply" -> ``Bash(gpend)``

## Multi-AI Parallel Collaboration
When multiple AIs need to work simultaneously (e.g., "let codex and gemini review together"):
- Option 1 (async): Run ``Bash(cask "...")`` and ``Bash(gask "...")`` in parallel, then use ``Bash(cpend)``/``Bash(gpend)`` to check results later
- Option 2 (sync sequential): Run ``Bash(cask-w "...")`` first, then ``Bash(gask-w "...")``, summarize both results
- Do NOT use run_in_background=true with cask-w/gask-w
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
