Forward commands to Codex session and wait for reply synchronously via `cask-w` command.

**CRITICAL: You MUST run this command synchronously (do NOT use `run_in_background=true`) and wait for it to finish.**

Execution:
1. Run `cask-w "<content>"`
2. The command will block until Codex replies (or times out).
3. The reply content will be in the command's standard output.

Parameters:
- `<content>` required, will be forwarded to Codex session

Example:
- `cask-w "analyze code"` -> (Wait for output...) -> "Here is the analysis..."

Hints:
- Use `cask` (no -w) only if you explicitly want fire-and-forget (no wait).
- Use `/cpend` to view latest reply if you missed it.