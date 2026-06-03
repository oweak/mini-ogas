"""CLI entry point — argument parsing and command dispatch."""

from __future__ import annotations

import argparse
import logging
import sys

from .commands import (
    up,
    down,
    status,
    doctor,
    guard,
    ai,
    demo,
    setup,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mogas",
        description="Mini-OGAS System Manager — orchestrate the entire dev/demo lifecycle.",
    )
    p.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    p.add_argument(
        "command",
        nargs="?",
        default="help",
        choices=["up", "down", "status", "doctor", "guard", "ai", "demo", "setup", "help"],
        help="Action to perform",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="(with up) Also start microservices and dashboard",
    )
    p.add_argument(
        "scenario",
        nargs="?",
        help="(with demo) Scenario name: normal|common_fault|complex_fault|market_shift|hostile_attack",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    dispatch: dict[str, callable] = {
        "up":     lambda: up.run(all=args.all),
        "down":   down.run,
        "status": status.run,
        "doctor": doctor.run,
        "guard":  guard.run,
        "ai":     ai.run,
        "demo":   lambda: demo.run(scenario=args.scenario or "normal"),
        "setup":  setup.run,
    }

    if args.command == "help":
        parser.print_help()
        print()
        _quickref()
        return

    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        sys.exit(1)

    try:
        fn()
    except KeyboardInterrupt:
        print("\n  Interrupted.")
        sys.exit(130)
    except Exception as exc:
        print(f"\n  ERROR: {exc}")
        if args.verbose:
            raise
        sys.exit(1)


def _quickref() -> None:
    print("Quick reference:")
    print("  mogas up                        Start core + agents")
    print("  mogas up --all                  Full stack (core + microservices + dashboard + agents)")
    print("  mogas down                      Stop everything")
    print("  mogas status                    Node health overview")
    print("  mogas doctor                    Environment diagnosis")
    print("  mogas guard                     Watch & alert on failures")
    print("  mogas ai                        AI backend connectivity")
    print("  mogas demo complex_fault        Inject fault scenario")
    print("  mogas setup                     Interactive .env wizard")
