# Claude Code Bridge - JetBrains IDE Plugin

A JetBrains IDE plugin that provides a native interface for Claude Code CLI.

## Features

- **Chat Tool Window**: Integrated chat panel in IDE sidebar
- **Context Injection**: Auto-inject selected code as context
- **Multi-AI Support**: Works with Claude, Codex, and Gemini via CCB
- **VFS Integration**: Real-time response monitoring via file system

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   IDEA Plugin                        │
│  ┌─────────────┐                                    │
│  │ ChatPanel   │──► stdin ──► Claude Code CLI       │
│  └─────────────┘                                    │
│         ▲                                           │
│         │                                           │
│  ┌─────────────┐                                    │
│  │FileWatcher  │◄── VFS ◄── session-*.json          │
│  └─────────────┘                                    │
└─────────────────────────────────────────────────────┘
```

## Building

```bash
cd ide-plugin
./gradlew buildPlugin
```

## Running (Development)

```bash
./gradlew runIde
```

## Installation

1. Build the plugin: `./gradlew buildPlugin`
2. Install from disk: Settings → Plugins → Install from Disk
3. Select `build/distributions/ccb-ide-plugin-*.zip`

## Configuration

Settings → Tools → Claude Code Bridge

- **CLI Path**: Path to `claude` executable (default: `claude`)
- **Default Provider**: Default AI provider (claude/codex/gemini)
- **Auto-inject Context**: Automatically include selected code
- **Show Notifications**: Display notification popups

## Usage

1. Open the "Claude Code Bridge" tool window (right sidebar)
2. Type your question and press Ctrl+Enter or click Send
3. Or: Select code → Right-click → "Ask AI..." (Ctrl+Alt+A)

## Project Structure

```
ide-plugin/
├── build.gradle.kts          # Gradle build config
├── settings.gradle.kts       # Project settings
├── gradle.properties         # Gradle properties
└── src/main/
    ├── kotlin/com/ccb/ide/
    │   ├── ui/               # UI components
    │   │   ├── ChatToolWindowFactory.kt
    │   │   └── ChatPanel.kt
    │   ├── backend/          # CLI communication
    │   │   ├── CliProcessManager.kt
    │   │   └── FileWatcherService.kt
    │   ├── actions/          # Editor actions
    │   │   └── AskAIAction.kt
    │   └── config/           # Settings
    │       ├── CcbSettings.kt
    │       └── CcbSettingsConfigurable.kt
    └── resources/
        └── META-INF/
            └── plugin.xml    # Plugin descriptor
```

## Requirements

- IntelliJ IDEA 2023.2+ (or compatible JetBrains IDE)
- Claude Code CLI installed (`claude` command available)
- Java 17+

## License

MIT
