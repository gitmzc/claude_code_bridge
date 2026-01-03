---
name: cask
description: "Use when user explicitly delegates to Codex (@codex, ask codex, 问codex, 让codex) AND says 'don't wait' or '不用等'. Asynchronous - send and return immediately."
---

# Ask Codex (Async)

Send a question to Codex AI assistant running in a separate terminal (fire-and-forget).

## Trigger Conditions

Use this skill when:
- User explicitly says "don't wait" / "不用等回复" / "异步发送"
- User wants to send a long-running task to Codex without blocking

**DO NOT trigger** when:
- User expects an immediate reply (use cask-w instead)
- User asks questions **about** Codex

## Execution

```
Bash(cask "$ARGUMENTS")
```

Where `$ARGUMENTS` is the user's delegation request (forwarded as-is to Codex).

## Context Awareness (IMPORTANT)

Codex runs in a separate terminal and **cannot see your current context**.
When sending questions, you MUST include:
- Relevant file paths
- Code snippets being discussed
- Error messages if debugging

## After Execution

1. Confirm the message was sent
2. Tell user they can use `cpend` to check for replies later
3. Continue with other tasks

## Checking Replies

Use `cpend` to view Codex's reply when ready:
- `cpend` - View latest reply
- `cpend N` - View last N conversation turns

## Parameters

- `--timeout SECONDS` optional (default 3600)
- `--output FILE` optional: write reply to FILE
