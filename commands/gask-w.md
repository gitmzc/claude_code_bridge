Forward commands to Gemini session and wait for reply synchronously via `gask-w` command.

**CRITICAL: You MUST run this command synchronously (do NOT use `run_in_background=true`) and wait for it to finish.**

Execution:
1. Run `gask-w "<content>"`
2. The command will block until Gemini replies (or times out).
3. The reply content will be in the command's standard output.

Parameters:
- `<content>` required, will be forwarded to Gemini session

Example:
- `gask-w "explain this"` -> (Wait for output...) -> "Here is the explanation..."

Hints:
- Use `gask` (no -w) only if you explicitly want fire-and-forget (no wait).
- Use `/gpend` to view latest reply if you missed it.