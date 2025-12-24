<div align="center">

# Claude Code Bridge (ccb) v3.0

**Multi-AI Collaboration: Claude + Codex + Gemini**

**Windows | macOS | Linux — One Tool, All Platforms**

[![Version](https://img.shields.io/badge/version-3.0-orange.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

[English](#english) | [中文](#中文)

<img src="assets/demo.webp" alt="Dual-pane demo" width="900">

</div>

---

# English

## What's New in v3.0

> **Simplified Architecture**

- **Removed tmux support** — Now uses WezTerm/iTerm2 only for cleaner, more reliable communication
- **Removed FIFO bridge** — Direct terminal injection for all platforms
- **Unified codebase** — Same communication pattern for Codex and Gemini

## Why This Project?

Traditional MCP calls treat Codex as a **stateless executor**—Claude must feed full context every time.

**ccb** establishes a **persistent, lightweight channel** for sending/receiving small messages while each AI maintains its own context.

### Division of Labor

| Role | Responsibilities |
|------|------------------|
| **Claude Code** | Requirements analysis, architecture planning, code refactoring |
| **Codex** | Algorithm implementation, bug hunting, code review |
| **Gemini** | Research, alternative perspectives, verification |
| **ccb** | Session management, context isolation, communication bridge |

### MCP vs Persistent Dual-Pane

| Aspect | MCP | Persistent Dual-Pane |
|--------|-----|----------------------|
| Codex State | Stateless | Persistent session |
| Context | Passed from Claude | Self-maintained |
| Token Cost | 5k-20k/call | 50-200/call |
| Work Mode | Master-slave | Parallel |
| Recovery | Not possible | Supported (`-r`) |

## Requirements

- Python 3.10+
- **WezTerm** (recommended, cross-platform) or **iTerm2** (macOS only)

> **Windows Users:** Install WezTerm using the native Windows .exe installer from [wezfurlong.org/wezterm](https://wezfurlong.org/wezterm/), even if you use WSL.

## Install

```bash
git clone https://github.com/bfly123/claude_code_bridge.git
cd claude_code_bridge
./install.sh install
```

### Windows

- **WSL2 (recommended):** run the same commands inside WSL
- **Native Windows:** use `install.cmd install` or `powershell -ExecutionPolicy Bypass -File .\install.ps1 install`

## Quick Start

```bash
ccb up codex            # Start with Codex
ccb up gemini           # Start with Gemini
ccb up codex gemini     # Start both
ccb up codex -r         # Resume previous session
ccb up codex -a         # Full permissions mode
```

### Session Management

```bash
ccb status              # Check backend status
ccb kill codex          # Terminate session
ccb restore codex       # Attach to running session
ccb doctor              # Diagnose issues
ccb update              # Update to latest version
```

## Commands

**Codex:**

| Command | Description |
|---------|-------------|
| `cask-w <msg>` | Sync: wait for reply |
| `cask <msg>` | Async: fire-and-forget |
| `cpend` | Show latest reply |
| `cpend N` | Show last N Q&A pairs |
| `cping` | Connectivity check |

**Gemini:**

| Command | Description |
|---------|-------------|
| `gask-w <msg>` | Sync: wait for reply |
| `gask <msg>` | Async: fire-and-forget |
| `gpend` | Show latest reply |
| `gpend N` | Show last N Q&A pairs |
| `gping` | Connectivity check |

## Uninstall

```bash
./install.sh uninstall
```

---

# 中文

## v3.0 新特性

> **简化架构**

- **移除 tmux 支持** — 现在仅使用 WezTerm/iTerm2，通信更简洁可靠
- **移除 FIFO 桥接** — 所有平台统一使用终端直接注入
- **统一代码库** — Codex 和 Gemini 使用相同的通信模式

## 为什么需要这个项目？

传统 MCP 调用把 Codex 当作**无状态执行器**——Claude 每次都要传递完整上下文。

**ccb** 建立**持久通道**，轻量级发送和抓取信息，AI 间各自维护独立上下文。

### 分工协作

| 角色 | 职责 |
|------|------|
| **Claude Code** | 需求分析、架构规划、代码重构 |
| **Codex** | 算法实现、bug 定位、代码审查 |
| **Gemini** | 研究、多角度分析、验证 |
| **ccb** | 会话管理、上下文隔离、通信桥接 |

### MCP vs 持久双窗口

| 维度 | MCP | 持久双窗口 |
|------|-----|-----------|
| Codex 状态 | 无记忆 | 持久会话 |
| 上下文 | Claude 传递 | 各自维护 |
| Token 消耗 | 5k-20k/次 | 50-200/次 |
| 工作模式 | 主从 | 并行协作 |
| 会话恢复 | 不支持 | 支持 (`-r`) |

## 依赖

- Python 3.10+
- **WezTerm**（推荐，跨平台）或 **iTerm2**（仅 macOS）

> **Windows 用户：** 必须使用 Windows 原生 .exe 安装包安装 WezTerm（[下载地址](https://wezfurlong.org/wezterm/)），即使使用 WSL 也是如此。

## 安装

```bash
git clone https://github.com/bfly123/claude_code_bridge.git
cd claude_code_bridge
./install.sh install
```

### Windows

- **推荐 WSL2：** 在 WSL 内执行上面的命令
- **原生 Windows：** 使用 `install.cmd install` 或 `powershell -ExecutionPolicy Bypass -File .\install.ps1 install`

## 快速开始

```bash
ccb up codex            # 启动 Codex
ccb up gemini           # 启动 Gemini
ccb up codex gemini     # 同时启动
ccb up codex -r         # 恢复上次会话
ccb up codex -a         # 最高权限模式
```

### 会话管理

```bash
ccb status              # 检查后端状态
ccb kill codex          # 终止会话
ccb restore codex       # 连接到运行中的会话
ccb doctor              # 诊断问题
ccb update              # 更新到最新版本
```

## 命令

**Codex:**

| 命令 | 说明 |
|------|------|
| `cask-w <消息>` | 同步：等待回复 |
| `cask <消息>` | 异步：发送即返回 |
| `cpend` | 查看最新回复 |
| `cpend N` | 查看最近 N 个问答对 |
| `cping` | 测试连通性 |

**Gemini:**

| 命令 | 说明 |
|------|------|
| `gask-w <消息>` | 同步：等待回复 |
| `gask <消息>` | 异步：发送即返回 |
| `gpend` | 查看最新回复 |
| `gpend N` | 查看最近 N 个问答对 |
| `gping` | 测试连通性 |

## 卸载

```bash
./install.sh uninstall
```
