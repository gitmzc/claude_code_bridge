#!/usr/bin/env python3
"""
Broadcast module for parallel AI communication.
Sends messages to multiple AI providers simultaneously and collects responses.
"""

from __future__ import annotations

import concurrent.futures
import sys
import time
from typing import Optional, Dict, Any, List

from i18n import t
from output import print_msg, print_error, is_json, set_output, flush_json


# Provider colors for terminal output
PROVIDER_COLORS = {
    "codex": "\033[94m",   # Blue
    "gemini": "\033[92m",  # Green
}
RESET_COLOR = "\033[0m"
BOLD = "\033[1m"


def _get_communicator(provider: str):
    """Lazy-load communicator for a provider."""
    if provider == "codex":
        from codex_comm import CodexCommunicator
        return CodexCommunicator(lazy_init=True)
    elif provider == "gemini":
        from gemini_comm import GeminiCommunicator
        return GeminiCommunicator(lazy_init=True)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _send_and_wait(provider: str, message: str, timeout: int) -> Dict[str, Any]:
    """Send message to a provider and wait for reply.

    Returns a dict with:
        - provider: str
        - success: bool
        - reply: Optional[str]
        - error: Optional[str]
        - elapsed: float (seconds)
    """
    start_time = time.time()
    result = {
        "provider": provider,
        "success": False,
        "reply": None,
        "error": None,
        "elapsed": 0.0,
    }

    try:
        comm = _get_communicator(provider)

        # Check health first
        healthy, status = comm._check_session_health_impl(probe_terminal=False)
        if not healthy:
            result["error"] = f"Session unhealthy: {status}"
            result["elapsed"] = time.time() - start_time
            return result

        # Send message and capture state
        if provider == "codex":
            marker, state = comm._send_message(message)
            reply, new_state = comm.log_reader.wait_for_message(state, float(timeout) if timeout > 0 else 600.0)
        else:  # gemini
            comm._send_via_terminal(message)
            state = comm.log_reader.capture_state()
            reply, new_state = comm.log_reader.wait_for_message(state, float(timeout) if timeout > 0 else 600.0)

        if reply:
            result["success"] = True
            result["reply"] = reply
        else:
            result["error"] = "Timeout waiting for reply"

    except Exception as e:
        result["error"] = str(e)

    result["elapsed"] = time.time() - start_time
    return result


def parallel_ask(
    message: str,
    providers: Optional[List[str]] = None,
    timeout: int = 0,
    wait: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Send message to multiple providers in parallel.

    Args:
        message: The message to send
        providers: List of providers (default: ["codex", "gemini"])
        timeout: Timeout in seconds (0 = unlimited)
        wait: Whether to wait for replies

    Returns:
        Dict mapping provider name to result dict
    """
    if providers is None:
        providers = ["codex", "gemini"]

    # Filter to only available providers
    available_providers = []
    for provider in providers:
        try:
            _get_communicator(provider)
            available_providers.append(provider)
        except Exception as e:
            print_error(f"[{provider}] Not available: {e}")

    if not available_providers:
        print_error("No providers available")
        return {}

    results: Dict[str, Dict[str, Any]] = {}

    if not wait:
        # Fire and forget mode
        for provider in available_providers:
            try:
                comm = _get_communicator(provider)
                comm.ask_async(message)
                results[provider] = {"provider": provider, "success": True, "sent": True}
            except Exception as e:
                results[provider] = {"provider": provider, "success": False, "error": str(e)}
        return results

    # Parallel wait mode
    print_msg(f"🔔 Sending to {', '.join(p.capitalize() for p in available_providers)}...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(available_providers)) as executor:
        future_to_provider = {
            executor.submit(_send_and_wait, provider, message, timeout): provider
            for provider in available_providers
        }

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_provider):
            provider = future_to_provider[future]
            try:
                result = future.result()
                results[provider] = result
            except Exception as e:
                results[provider] = {
                    "provider": provider,
                    "success": False,
                    "error": str(e),
                    "elapsed": 0.0,
                }

    return results


def format_results(results: Dict[str, Dict[str, Any]], use_color: bool = True) -> str:
    """Format results for display.

    Args:
        results: Dict of provider results
        use_color: Whether to use ANSI colors

    Returns:
        Formatted string
    """
    lines = []

    for provider, result in results.items():
        color = PROVIDER_COLORS.get(provider, "") if use_color else ""
        reset = RESET_COLOR if use_color else ""
        bold = BOLD if use_color else ""

        # Header
        elapsed = result.get("elapsed", 0)
        elapsed_str = f" ({elapsed:.1f}s)" if elapsed > 0 else ""
        lines.append(f"\n{bold}{color}{'=' * 20} {provider.upper()}{elapsed_str} {'=' * 20}{reset}")

        if result.get("success"):
            reply = result.get("reply", "")
            lines.append(reply)
        else:
            error = result.get("error", "Unknown error")
            lines.append(f"Error: {error}")

    return "\n".join(lines)


def cmd_ask(args) -> int:
    """Handle the 'ccb ask' command."""
    # Get message
    message = " ".join(args.message).strip() if args.message else ""
    if not message:
        print_error("Please provide a message")
        return 1

    # Determine providers
    if args.all:
        providers = ["codex", "gemini"]
    elif args.providers:
        providers = [p.strip().lower() for p in args.providers.split(",")]
    else:
        providers = ["codex", "gemini"]  # Default to all

    # Validate providers
    valid_providers = {"codex", "gemini"}
    invalid = set(providers) - valid_providers
    if invalid:
        print_error(f"Invalid providers: {', '.join(invalid)}")
        return 1

    # Execute
    timeout = getattr(args, "timeout", 0) or 0
    wait = getattr(args, "wait", True)

    results = parallel_ask(
        message=message,
        providers=providers,
        timeout=timeout,
        wait=wait,
    )

    if not results:
        return 1

    # Output
    if is_json():
        set_output("results", results)
        return flush_json(0)

    # Check if stdout is a TTY for color support
    use_color = sys.stdout.isatty()
    print(format_results(results, use_color=use_color))

    # Return non-zero if any provider failed
    if any(not r.get("success") for r in results.values()):
        return 1

    return 0


def main() -> int:
    """CLI entry point for broadcast module."""
    import argparse

    parser = argparse.ArgumentParser(description="Send message to multiple AI providers")
    parser.add_argument("message", nargs="*", help="Message to send")
    parser.add_argument("-p", "--providers", type=str, help="Comma-separated providers (codex,gemini)")
    parser.add_argument("-a", "--all", action="store_true", help="Send to all providers")
    parser.add_argument("-w", "--wait", action="store_true", default=True, help="Wait for replies (default)")
    parser.add_argument("--no-wait", action="store_true", help="Fire and forget mode")
    parser.add_argument("-t", "--timeout", type=int, default=0, help="Timeout in seconds (0=unlimited)")

    args = parser.parse_args()

    # Handle --no-wait flag
    if args.no_wait:
        args.wait = False

    return cmd_ask(args)


if __name__ == "__main__":
    raise SystemExit(main())
