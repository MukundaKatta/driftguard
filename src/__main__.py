"""CLI for driftguard."""
import sys, json, argparse
from .core import Driftguard

def main():
    parser = argparse.ArgumentParser(description="Your ML models are drifting. We'll catch it.")
    parser.add_argument("command", nargs="?", default="status", choices=["status", "run", "info"])
    parser.add_argument("--input", "-i", default="")
    args = parser.parse_args()
    instance = Driftguard()
    if args.command == "status":
        print(json.dumps(instance.get_stats(), indent=2))
    elif args.command == "run":
        print(json.dumps(instance.process(input=args.input or "test"), indent=2, default=str))
    elif args.command == "info":
        print(f"driftguard v0.1.0 — Your ML models are drifting. We'll catch it.")

if __name__ == "__main__":
    main()
