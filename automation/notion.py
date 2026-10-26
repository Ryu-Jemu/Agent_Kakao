"""Write only managed pages directly inside the approved PR evidence container."""

import hashlib
import json
import re
import time

from .evidence import REPOSITORY, SHA
from .http import AmbiguousWrite, AutomationError

PROJECT_PAGE_ID = "405abd87-fe45-80ab-9dd5-c430c8dce2e1"
RECORDS_PAGE_ID = "405abd87-fe45-81fe-b786-c55d929dd654"
MARKER = "AI_TOP_100_EVIDENCE_V1"
FIELDS = (
    "record_key", "repository", "task_id", "pr_number", "pr_url", "base_branch", "base_sha",
    "head_sha", "tested_sha", "merge_sha", "author", "implementation_agent", "summary", "changed_files",
    "commits", "test_commands", "test_results", "ci_status", "workflow_run_url",
    "known_issues", "risks", "evidence_links", "review_status", "next_actions",
    "created_at", "updated_at", "pr_updated_at", "merged", "state",
)


def normalize_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9-]{32,36}", value):
        raise AutomationError("Invalid Notion page ID")
    return value.replace("-", "").lower()


def validate_report(report):
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise AutomationError("Unsupported evidence schema")
    if any(field not in report for field in FIELDS):
        raise AutomationError("Incomplete evidence report")
    if not REPOSITORY.fullmatch(report.get("repository", "")) or not SHA.fullmatch(report.get("head_sha", "")):
        raise AutomationError("Invalid evidence repository or SHA")
    if type(report.get("repository_id")) is not int or type(report.get("pr_number")) is not int:
        raise AutomationError("Invalid evidence repository/PR identifier")
    expected = f"{report['repository_id']}:{report['pr_number']}:{report['head_sha']}"
    if report["record_key"] != expected:
        raise AutomationError("Evidence record key mismatch")
    if report["review_status"] != "PENDING_REVIEW":
        raise AutomationError("Automation cannot assert a human review result")


def paragraph(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "text": {"content": text[index:index + 1900]}}
        for index in range(0, len(text), 1900)
    ]}}


def block_text(block):
    if block.get("type") != "paragraph":
        raise AutomationError("Managed record contains an unexpected block type")
    return "".join(item.get("plain_text", item.get("text", {}).get("content", ""))
                   for item in block["paragraph"]["rich_text"])


def render(report):
    validate_report(report)
    # Keep the full evidence in the GitHub artifact. Notion is a readable bounded
    # view, with explicit truncation and source links, never a silent lossy copy.
    texts = []
    for field in FIELDS:
        value = json.dumps(report[field], ensure_ascii=False, indent=2)
        if field == "test_results":
            if len(value) > 60000:
                raise AutomationError("CI history exceeds document budget; archive policy required before another update")
        elif len(value) > 4000:
            value = value[:4000] + "\n[TRUNCATED: see GitHub source links and evidence.json artifact for full evidence]"
        texts.append(field + "\n" + value)
    digest = hashlib.sha256("\n".join(texts).encode()).hexdigest()
    blocks = [paragraph(f"{MARKER}\n{report['record_key']}\nsha256:{digest}"), *map(paragraph, texts)]
    if len(json.dumps(blocks, ensure_ascii=False).encode()) > 450000:
        raise AutomationError("Notion evidence exceeds payload budget; retain the GitHub artifact and review archive policy")
    return blocks


class Notion:
    def __init__(self, client, parent_id, *, sleep=time.sleep):
        if normalize_id(parent_id) != normalize_id(RECORDS_PAGE_ID):
            raise AutomationError("Notion parent is outside the approved records container")
        self.client = client
        self.parent_id = RECORDS_PAGE_ID
        self.sleep = sleep

    def _check_parent(self):
        page = self.client.request("GET", f"/pages/{self.parent_id}")
        parent = page.get("parent", {})
        if parent.get("type") != "page_id" or normalize_id(parent.get("page_id", "")) != normalize_id(PROJECT_PAGE_ID):
            raise AutomationError("Approved records container is not directly inside the approved project")
        if page.get("archived") or page.get("in_trash"):
            raise AutomationError("Approved records container is archived")

    def _children(self, block_id):
        items, cursor = [], None
        for _ in range(100):
            from urllib.parse import urlencode
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            result = self.client.request("GET", f"/blocks/{block_id}/children?" + urlencode(params))
            items.extend(result["results"])
            if not result.get("has_more"):
                return items
            cursor = result.get("next_cursor")
            if not cursor:
                raise AutomationError("Notion pagination cursor missing")
        raise AutomationError("Notion pagination limit reached")

    def _find(self, title, key):
        matches = []
        for item in self._children(self.parent_id):
            if item.get("type") != "child_page":
                continue
            if item["child_page"]["title"] == title:
                matches.append(item["id"])
                continue
            # Titles are editable. Inspect the stable ownership marker before
            # concluding that a record does not exist.
            result = self.client.request("GET", f"/blocks/{item['id']}/children?page_size=1")
            first = (result.get("results") or [None])[0]
            if first and first.get("type") == "paragraph" and block_text(first).startswith(f"{MARKER}\n{key}\nsha256:"):
                matches.append(item["id"])
        if len(matches) > 1:
            raise AutomationError("Duplicate record pages exist; manual reconciliation required")
        return matches[0] if matches else None

    def _read(self, page_id, key):
        page = self.client.request("GET", f"/pages/{page_id}")
        parent = page.get("parent", {})
        if parent.get("type") != "page_id" or normalize_id(parent.get("page_id", "")) != normalize_id(self.parent_id):
            raise AutomationError("Record page parent is outside the approved container")
        if page.get("archived") or page.get("in_trash"):
            raise AutomationError("Record page is archived")
        blocks = self._children(page_id)
        if len(blocks) != len(FIELDS) + 1:
            raise AutomationError("Managed record block count differs; preserve contents for manual review")
        texts = [block_text(item) for item in blocks]
        if not texts[0].startswith(f"{MARKER}\n{key}\nsha256:"):
            raise AutomationError("Record ownership marker mismatch")
        for field, value in zip(FIELDS, texts[1:]):
            if not value.startswith(field + "\n"):
                raise AutomationError("Managed record field order changed; manual review required")
        return page, blocks, texts

    def publish(self, report):
        validate_report(report)
        self._check_parent()
        title = f"PR #{report['pr_number']} | {report['repository_id']} | {report['head_sha']}"
        page_id = self._find(title, report["record_key"])
        action = "updated"
        if page_id:
            page, current, texts = self._read(page_id, report["record_key"])
            # Preserve the record's initial timestamp, even after a rerun.
            report = dict(report)
            report["created_at"] = json.loads(texts[FIELDS.index("created_at") + 1].split("\n", 1)[1])
            previous_runs = json.loads(texts[FIELDS.index("test_results") + 1].split("\n", 1)[1])
            if not isinstance(previous_runs, list):
                raise AutomationError("Stored CI history is invalid; manual review required")
            combined = {(item["run_id"], item["run_attempt"]): item for item in previous_runs}
            combined.update({(item["run_id"], item["run_attempt"]): item for item in report["test_results"]})
            report["test_results"] = [combined[key] for key in sorted(combined)]
            report["evidence_links"] = list(dict.fromkeys([
                *report["evidence_links"], *[item["url"] for item in report["test_results"]]
            ]))
            desired = render(report)
            # Update the marker last: an interrupted write remains visibly incomplete
            # and a subsequent run reconciles every managed field.
            for index in [*range(1, len(desired)), 0]:
                if block_text(desired[index]) != texts[index]:
                    self.client.request("PATCH", f"/blocks/{current[index]['id']}",
                                        {"paragraph": desired[index]["paragraph"]}, idempotent=True)
            if texts == [block_text(item) for item in desired]:
                action = "unchanged"
        else:
            desired = render(report)
            body = {"parent": {"type": "page_id", "page_id": self.parent_id},
                    "properties": {"title": {"type": "title", "title": [
                        {"type": "text", "text": {"content": title}}
                    ]}}, "children": desired}
            try:
                created = self.client.request("POST", "/pages", body)
                page_id = created["id"]
                action = "created"
            except AmbiguousWrite as error:
                # A POST can commit before a timeout. Never submit a second POST
                # automatically, even when the first lookup has not indexed it yet.
                committed = error.data.get("additional_data", {}).get("committed_resource_id")
                if committed:
                    normalize_id(committed)
                    page_id = committed
                else:
                    for attempt in range(3):
                        self.sleep(attempt + 1)
                        page_id = self._find(title, report["record_key"])
                        if page_id:
                            break
                if not page_id:
                    raise AutomationError("Notion create outcome unknown. No duplicate POST sent; reconcile this record key before rerun.") from None
                action = "reconciled"
        page, _, texts = self._read(page_id, report["record_key"])
        if texts != [block_text(item) for item in desired]:
            raise AutomationError("Notion read-back differs from intended evidence; retry reconciliation")
        return {"status": action, "page_id": page_id, "url": page["url"],
                "record_key": report["record_key"], "readback_verified": True}
