"""CLI used by trusted workflows; all source strings remain JSON data."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

from .evidence import GitHub, NoMatchingPR
from .http import AutomationError, JsonClient
from .notion import Notion, PROJECT_PAGE_ID, normalize_id, render


def required(name):
    value = os.environ.get(name)
    if not value:
        raise AutomationError(f"Missing required environment variable: {name}")
    return value


def sanitize(value):
    if isinstance(value, str):
        for name in ("GITHUB_TOKEN", "NOTION_TOKEN"):
            secret = os.environ.get(name)
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|ntn_[A-Za-z0-9]{20,}|secret_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})\b", "[REDACTED]", value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    return value


def write_json(path, data):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(sanitize(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "sync"):
        child = subparsers.add_parser(command)
        child.add_argument("--pr", type=int)
        child.add_argument("--run-id", type=int)
        child.add_argument("--run-attempt", type=int)
        child.add_argument("--event-file", help="GitHub workflow_run event JSON; pins run ID and attempt")
        child.add_argument("--output", default="artifacts/evidence.json")
        if command == "sync":
            child.add_argument("--dry-run", action="store_true")
    publish = subparsers.add_parser("publish")
    publish.add_argument("--input", required=True)
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--output", default="artifacts/publication.json")
    args = parser.parse_args(argv)
    try:
        if args.command in ("collect", "sync"):
            run_id = args.run_id
            run_attempt = args.run_attempt
            if args.event_file:
                event = json.loads(Path(args.event_file).read_text(encoding="utf-8"))
                event_run = event.get("workflow_run", {})
                if event_run.get("id") is None:
                    raise AutomationError("Event JSON is not a workflow_run event; supply --pr or --run-id")
                if run_id is not None and run_id != event_run["id"]:
                    raise AutomationError("Explicit run ID differs from event run ID")
                run_id = event_run["id"]
                if type(event_run.get("run_attempt")) is not int:
                    raise AutomationError("Event workflow run attempt is missing")
                if run_attempt is not None and run_attempt != event_run["run_attempt"]:
                    raise AutomationError("Explicit run attempt differs from event attempt")
                run_attempt = event_run["run_attempt"]
            client = JsonClient("https://api.github.com", required("GITHUB_TOKEN"), headers={
                "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"
            })
            report = sanitize(GitHub(client, required("GITHUB_REPOSITORY")).collect(args.pr, run_id, run_attempt))
            write_json(args.output, report)
            if args.command == "collect":
                print(json.dumps({"status": "collected", "record_key": report["record_key"], "output": args.output}))
                return 0
        else:
            source = Path(args.input)
            if source.stat().st_size > 5_000_000:
                raise AutomationError("Evidence input exceeds safety limit")
            report = sanitize(json.loads(source.read_text(encoding="utf-8")))
        if args.dry_run:
            blocks = render(report)
            print(json.dumps({"status": "dry_run", "record_key": report["record_key"], "block_count": len(blocks), "notion_write": False}))
            return 0
        project_override = os.environ.get("NOTION_PROJECT_PAGE_ID")
        if project_override and normalize_id(project_override) != normalize_id(PROJECT_PAGE_ID):
            raise AutomationError("Project page override differs from approved scope")
        notion = Notion(JsonClient("https://api.notion.com/v1", required("NOTION_TOKEN"), headers={
            "Notion-Version": "2026-03-11"
        }), required("NOTION_PARENT_PAGE_ID"))
        result = notion.publish(report)
        output = args.output if args.command == "publish" else str(Path(args.output).with_name("publication.json"))
        write_json(output, result)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except NoMatchingPR as error:
        result = {"status": "skipped", "reason": str(error), "notion_write": False}
        write_json(args.output, result)
        print(json.dumps(result))
        return 0
    except (AutomationError, OSError, ValueError, KeyError, TypeError) as error:
        message = str(error) if isinstance(error, AutomationError) else "Invalid input or unexpected API schema; inspect source metadata and retry"
        print(json.dumps({"status": "failed", "error": sanitize(message)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
