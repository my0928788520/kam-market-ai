"""Command-line entry point for local authorization dry-runs."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .bootstrap import AuthorizationBootstrap, AuthorizationFailure, AuthorizationSettings


def main(argv: Sequence[str] | None = None, bootstrap: AuthorizationBootstrap | None = None) -> int:
    parser = argparse.ArgumentParser(description="KAM local Fubon market-data authorization")
    parser.add_argument("--env", default=".env", help="local .env path; never printed")
    parser.add_argument("--live", action="store_true", help="explicitly perform local authorization")
    parser.add_argument("--interactive", action="store_true", help="prompt locally instead of reading .env")
    args = parser.parse_args(argv)
    if args.interactive and not args.live:
        parser.error("--interactive requires explicit --live; default dry-run never prompts")
    try:
        settings = AuthorizationSettings.from_interactive_prompt() if args.interactive else AuthorizationSettings.from_local_env(args.env)
        result = (bootstrap or AuthorizationBootstrap()).run(settings, dry_run=not args.live)
    except AuthorizationFailure as error:
        print(f"failure_stage={error.stage.value}")
        return 2
    if result.dry_run:
        print(f"DRY-RUN: configuration checked; missing_fields={len(result.missing_fields)}")
        return 0
    print("AUTHORIZED: market-data clients created; no subscriptions or REST requests were made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
