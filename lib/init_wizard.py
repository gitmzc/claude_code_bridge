#!/usr/bin/env python3
"""
ccb init - Interactive configuration wizard
Guides users through first-time setup
"""

import os
import sys
import json
import shutil
import platform
from pathlib import Path
from typing import Optional, Dict, Any, List


def detect_terminal_backends() -> Dict[str, bool]:
    """Detect available terminal backends"""
    backends = {
        "wezterm": False,
        "iterm2": False,
        "tmux": False,
    }

    # Check WezTerm
    if shutil.which("wezterm"):
        backends["wezterm"] = True

    # Check iTerm2 (macOS only)
    if platform.system() == "Darwin":
        if shutil.which("it2") or Path("/Applications/iTerm.app").exists():
            backends["iterm2"] = True

    # Check tmux
    if shutil.which("tmux"):
        backends["tmux"] = True

    return backends


def detect_ai_tools() -> Dict[str, bool]:
    """Detect installed AI CLI tools"""
    tools = {
        "codex": shutil.which("codex") is not None,
        "gemini": shutil.which("gemini") is not None,
    }
    return tools


def get_recommended_backend(backends: Dict[str, bool]) -> Optional[str]:
    """Get recommended terminal backend based on platform"""
    system = platform.system()

    # WezTerm is recommended for all platforms
    if backends["wezterm"]:
        return "wezterm"

    # iTerm2 for macOS
    if system == "Darwin" and backends["iterm2"]:
        return "iterm2"

    # tmux as fallback
    if backends["tmux"]:
        return "tmux"

    return None


def prompt_choice(prompt: str, choices: List[str], default: Optional[str] = None) -> str:
    """Prompt user to select from choices"""
    # Check for non-interactive environment
    if not sys.stdin.isatty():
        if default and default in choices:
            print(f"Non-interactive mode: using default '{default}'")
            return default
        elif choices:
            print(f"Non-interactive mode: using first choice '{choices[0]}'")
            return choices[0]
        else:
            print("Error: No choices available in non-interactive mode")
            sys.exit(1)

    print(f"\n{prompt}")
    for i, choice in enumerate(choices, 1):
        marker = " (recommended)" if choice == default else ""
        print(f"  {i}. {choice}{marker}")

    # Calculate default index safely
    default_idx = None
    if default and default in choices:
        default_idx = choices.index(default) + 1

    while True:
        try:
            if default_idx:
                user_input = input(f"\nEnter choice [1-{len(choices)}] (default: {default_idx}): ").strip()
            else:
                user_input = input(f"\nEnter choice [1-{len(choices)}]: ").strip()

            if not user_input and default and default in choices:
                return default

            idx = int(user_input) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
            print(f"Please enter a number between 1 and {len(choices)}")
        except ValueError:
            print("Please enter a valid number")
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            sys.exit(1)


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    """Prompt user for yes/no answer"""
    # Check for non-interactive environment
    if not sys.stdin.isatty():
        print(f"Non-interactive mode: using default '{'yes' if default else 'no'}'")
        return default

    default_str = "Y/n" if default else "y/N"
    while True:
        try:
            user_input = input(f"{prompt} [{default_str}]: ").strip().lower()
            if not user_input:
                return default
            if user_input in ("y", "yes"):
                return True
            if user_input in ("n", "no"):
                return False
            print("Please enter 'y' or 'n'")
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            sys.exit(1)


def run_init_wizard(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Run the interactive configuration wizard"""
    print("=" * 50)
    print("  ccb init - Configuration Wizard")
    print("=" * 50)

    config: Dict[str, Any] = {}

    # Step 1: Detect environment
    print("\n[1/4] Detecting environment...")

    backends = detect_terminal_backends()
    ai_tools = detect_ai_tools()

    available_backends = [k for k, v in backends.items() if v]
    print(f"  Terminal backends: {', '.join(available_backends) if available_backends else 'None found'}")
    print(f"  AI tools: Codex {'✓' if ai_tools['codex'] else '✗'}, Gemini {'✓' if ai_tools['gemini'] else '✗'}")

    if not available_backends:
        print("\n⚠️  No terminal backend found!")
        print("   Please install one of: WezTerm (recommended), iTerm2 (macOS), or tmux")
        print("   Then run 'ccb init' again.")
        return {}

    # Step 2: Select terminal backend
    print("\n[2/4] Terminal backend selection")
    recommended = get_recommended_backend(backends)

    if len(available_backends) == 1:
        config["terminal"] = available_backends[0]
        print(f"  Using: {config['terminal']} (only available option)")
    else:
        config["terminal"] = prompt_choice(
            "Select terminal backend:",
            available_backends,
            default=recommended
        )

    # Step 3: Select default AI providers
    print("\n[3/4] AI provider configuration")

    available_providers = [k for k, v in ai_tools.items() if v]
    if not available_providers:
        print("  ⚠️  No AI CLI tools found!")
        print("     Install Codex: npm install -g @openai/codex")
        print("     Install Gemini: npm install -g @google/gemini-cli")
        config["default_providers"] = []
    else:
        if len(available_providers) == 1:
            config["default_providers"] = available_providers
            print(f"  Default provider: {available_providers[0]}")
        else:
            use_both = prompt_yes_no("Use both Codex and Gemini as default providers?", default=True)
            if use_both:
                config["default_providers"] = ["codex", "gemini"]
            else:
                provider = prompt_choice(
                    "Select default AI provider:",
                    available_providers,
                    default="codex" if "codex" in available_providers else available_providers[0]
                )
                config["default_providers"] = [provider]

    # Step 4: Additional options
    print("\n[4/4] Additional options")

    # Auto mode
    config["auto_mode"] = prompt_yes_no(
        "Enable auto mode by default (full auto permission)?",
        default=False
    )

    # Heartbeat interval
    config["heartbeat_interval"] = 30

    # Summary
    print("\n" + "=" * 50)
    print("  Configuration Summary")
    print("=" * 50)
    print(f"  Terminal backend: {config['terminal']}")
    print(f"  Default providers: {', '.join(config['default_providers']) if config['default_providers'] else 'None'}")
    print(f"  Auto mode: {'Enabled' if config['auto_mode'] else 'Disabled'}")

    # Confirm and save
    if not prompt_yes_no("\nSave this configuration?", default=True):
        print("Configuration not saved.")
        return {}

    # Determine config path
    if config_path is None:
        config_path = Path.cwd() / ".ccb-config.json"

    # Save configuration
    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Configuration saved to: {config_path}")
    except Exception as e:
        print(f"\n❌ Failed to save configuration: {e}")
        return {}

    # Post-setup hints
    print("\n" + "=" * 50)
    print("  Next Steps")
    print("=" * 50)
    print("  1. Start AI backends: ccb up")
    print("  2. Check status: ccb status")
    print("  3. Run diagnostics: ccb doctor")

    return config


def main() -> int:
    """Main entry point for ccb init"""
    import argparse

    parser = argparse.ArgumentParser(description="ccb configuration wizard")
    parser.add_argument(
        "--config", "-c",
        type=Path,
        help="Path to save configuration file"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing configuration"
    )
    args = parser.parse_args()

    # Check for existing config
    config_path = args.config or Path.cwd() / ".ccb-config.json"
    if config_path.exists() and not args.force:
        print(f"Configuration file already exists: {config_path}")
        if not prompt_yes_no("Overwrite existing configuration?", default=False):
            print("Use --force to overwrite, or specify a different path with --config")
            return 1

    config = run_init_wizard(config_path)
    return 0 if config else 1


if __name__ == "__main__":
    sys.exit(main())
