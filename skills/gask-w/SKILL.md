---
name: gask-w
description: "Use when user explicitly delegates to Gemini (@gemini, ask gemini, let gemini, 问gemini, 让gemini, 请gemini). Synchronous - waits for reply."
---

# Ask Gemini (Synchronous)

Send a question to Gemini AI assistant and wait for the reply synchronously.

## Trigger Conditions

Use this skill ONLY when user **explicitly delegates** to Gemini:
- User says "@gemini" / "ask gemini" / "let gemini" / "问gemini" / "让gemini" / "请gemini" + action verb
- User requests Gemini to review/analyze/suggest/debug/help with code or design
- User says "/gask-w" explicitly

**DO NOT trigger** when:
- User asks questions **about** Gemini (e.g., "What is Gemini?", "How does Gemini work?")
- User mentions Gemini in passing without delegation intent

## Execution (MANDATORY)

**CRITICAL: Run synchronously - DO NOT use run_in_background=true**

```
Bash(gask-w "$ARGUMENTS")
```

Where `$ARGUMENTS` is the user's delegation request (forwarded as-is to Gemini).

## Context Awareness (IMPORTANT)

Gemini runs in a separate terminal and **cannot see your current context**.
When sending questions, you MUST include:
- Relevant file paths
- Code snippets being discussed
- Error messages if debugging

**Wrong:**
```
gask-w "解释一下这个"
```

**Right:**
```
gask-w "解释 src/auth.ts 中的认证流程:
async function authenticate(token) {
    // ... code snippet ...
}
"
```

## After Execution

The tool output will contain Gemini's reply directly. You can:
1. Summarize the reply for the user
2. Take action based on Gemini's suggestions
3. Continue the conversation

## Note on Multi-Message Replies

Gemini may respond with multiple messages. The `gask-w` command will wait and collect all messages until the reply is complete.

## Error Handling

If gask-w times out:
1. Use `gpend` to check for delayed replies
2. Suggest user check if Gemini session is running (`ccb status gemini`)

## Parameters

- `--timeout SECONDS` optional (default from CCB_TIMEOUT or 300)
