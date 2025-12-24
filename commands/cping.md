Use `cping` to check if current Codex session is healthy, quickly locate communication issues.

Execution:
- Run `Bash(cping)` on Claude side, no need to output command execution process
- Run `cping` directly in local terminal

Detection items:
1. Is `.codex-session` marked as active
2. WezTerm mode: Does pane still exist (detected via `wezterm cli list`)
3. iTerm2 mode: Does session still exist

Output:
- Success: `Codex connection OK (...)`
- Failure: Lists missing components or error info for further troubleshooting

Hints:
- If detection fails, try re-running `ccb up codex`
- On multiple timeouts or no response, run `cping` first before deciding to restart session
