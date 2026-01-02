---
name: cask-w
description: Forward commands to Codex session and wait for reply synchronously via `cask-w` command.
---

# Ask Codex (Synchronous)

Send a question to Codex AI assistant and wait for the reply synchronously.

## Trigger Conditions

Use this skill ONLY when user **explicitly delegates** to Codex:
- User says "@codex" / "ask codex" / "let codex" / "问codex" / "让codex" / "请codex" + action verb
- User requests Codex to review/analyze/suggest/debug/help with code or design
- User says "/cask-w" explicitly

**DO NOT trigger** when:
- User asks questions **about** Codex (e.g., "What is Codex?", "How does Codex work?")
- User mentions Codex in passing without delegation intent

## Execution (MANDATORY)

**CRITICAL: Run synchronously - DO NOT use run_in_background=true**

```
Bash(cask-w "$ARGUMENTS")
```

Where `$ARGUMENTS` is the user's delegation request (forwarded as-is to Codex).

## Context Awareness (IMPORTANT)

Codex runs in a separate terminal and **cannot see your current context**.
When sending questions, you MUST include:
- Relevant file paths
- Code snippets being discussed
- Error messages if debugging

**Wrong:**
```
cask-w "重构这个函数"
```

**Right:**
```
cask-w "重构 lib/utils.py 中的 process_data 函数:
def process_data(data):
    # ... code snippet ...
"
```

## After Execution

The tool output will contain Codex's reply directly. You can:
1. Summarize the reply for the user
2. Take action based on Codex's suggestions
3. Continue the conversation

## Error Handling

If cask-w times out:
1. Use `cpend` to check for delayed replies
2. Suggest user check if Codex session is running (`ccb status codex`)

## Parameters

- `--timeout SECONDS` optional (default from CCB_TIMEOUT or 300)
