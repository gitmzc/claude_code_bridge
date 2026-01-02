---
name: gask
description: Forward commands to Gemini session via `gask` command (supports WezTerm / iTerm2, forward only, does not wait for reply).
---

# Ask Gemini (Async)

Send a question to Gemini AI assistant running in a separate terminal (fire-and-forget).

## Trigger Conditions

Use this skill when:
- User explicitly says "don't wait" / "不用等回复" / "异步发送"
- User wants to send a long-running task to Gemini without blocking

**DO NOT trigger** when:
- User expects an immediate reply (use gask-w instead)
- User asks questions **about** Gemini

## Execution

```
Bash(gask "$ARGUMENTS")
```

Where `$ARGUMENTS` is the user's delegation request (forwarded as-is to Gemini).

## Context Awareness (IMPORTANT)

Gemini runs in a separate terminal and **cannot see your current context**.
When sending questions, you MUST include:
- Relevant file paths
- Code snippets being discussed
- Error messages if debugging

## After Execution

1. Confirm the message was sent
2. Tell user they can use `gpend` to check for replies later
3. Continue with other tasks

## Checking Replies

Use `gpend` to view Gemini's reply when ready:
- `gpend` - View latest reply
- `gpend N` - View last N conversation turns

## Parameters

- `--timeout SECONDS` optional (default 3600)
- `--output FILE` optional: write reply to FILE
