import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from urllib.parse import parse_qs, urlsplit

from automation.cli import main, sanitize
from automation.evidence import GitHub, NoMatchingPR
from automation.http import AmbiguousWrite, ApiError, AutomationError, JsonClient
from automation.notion import FIELDS, Notion, PROJECT_PAGE_ID, RECORDS_PAGE_ID, block_text, render

HEAD = "a" * 40
MERGE = "b" * 40


class GitHubFixture:
    def __init__(self):
        self.pr = {
            "number": 1, "base": {"repo": {"id": 42, "full_name": "Ryu-Jemu/Agent_Kakao"},
                                     "sha": "c" * 40, "ref": "main"},
            "head": {"sha": HEAD}, "merge_commit_sha": MERGE, "merged": False,
            "changed_files": 1, "commits": 1, "html_url": "https://github.com/Ryu-Jemu/Agent_Kakao/pull/1",
            "user": {"login": "author"}, "title": 'literal $(touch /tmp/unsafe) ${TOKEN}',
            "updated_at": "2026-10-26T00:00:00Z", "state": "open",
        }
        self.run = {
            "id": 9, "run_attempt": 2, "repository": self.pr["base"]["repo"],
            "pull_requests": [{"number": 1, "base": self.pr["base"]}],
            "head_sha": HEAD, "event": "pull_request", "workflow_id": 8,
            "name": "CI", "status": "completed", "conclusion": "failure",
            "html_url": "https://github.com/Ryu-Jemu/Agent_Kakao/actions/runs/9",
        }
        self.files = [{"filename": "app.py", "status": "added", "sha": HEAD,
                       "additions": 10, "deletions": 0, "changes": 10,
                       "blob_url": f"https://github.com/Ryu-Jemu/Agent_Kakao/blob/{HEAD}/app.py"}]
        self.calls = []
        self.change_on_second_read = False
        self.path = ".github/workflows/ci.yml"
        self.associations = [self.pr]

    def request(self, method, path, body=None, **kwargs):
        self.calls.append((method, path))
        url = urlsplit(path)
        suffix = url.path.removeprefix("/repos/Ryu-Jemu/Agent_Kakao")
        if suffix in ("/actions/runs/9", "/actions/runs/9/attempts/2"):
            return copy.deepcopy(self.run)
        if suffix == "/actions/workflows/8":
            return {"path": self.path}
        if suffix == "/pulls/1":
            result = copy.deepcopy(self.pr)
            reads = sum(p.endswith("/pulls/1") for _, p in self.calls)
            if self.change_on_second_read and reads == 2:
                result["head"]["sha"] = "d" * 40
            return result
        if suffix.endswith("/pulls") and suffix.startswith("/commits/"):
            return copy.deepcopy(self.associations)
        if suffix == "/pulls/1/files":
            page = int(parse_qs(url.query)["page"][0])
            return copy.deepcopy(self.files[(page - 1) * 100:page * 100])
        if suffix == "/pulls/1/commits":
            return [{"sha": HEAD, "html_url": f"https://github.com/Ryu-Jemu/Agent_Kakao/commit/{HEAD}"}]
        if suffix == "/actions/runs/9/attempts/2/jobs":
            return {"jobs": [{"id": 91, "name": "tests", "status": "completed", "conclusion": "failure",
                              "html_url": "https://github.com/Ryu-Jemu/Agent_Kakao/actions/runs/9/job/91",
                              "steps": [{"name": "Run tests", "number": 1, "status": "completed", "conclusion": "failure"}]}]}
        if suffix == "/actions/runs":
            return {"workflow_runs": [copy.deepcopy(self.run)]}
        raise AssertionError((method, path))


def evidence():
    return GitHub(GitHubFixture(), "Ryu-Jemu/Agent_Kakao").collect(1, 9)


class NotionFixture:
    def __init__(self):
        self.pages = {}
        self.blocks = {}
        self.calls = []
        self.parent = PROJECT_PAGE_ID
        self.ambiguous = False
        self.hide_created = False
        self.corrupt_readback = False

    def request(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, copy.deepcopy(body)))
        path = path.split("?", 1)[0]
        if method == "GET" and path == f"/pages/{RECORDS_PAGE_ID}":
            return {"parent": {"type": "page_id", "page_id": self.parent}}
        if method == "GET" and path == f"/blocks/{RECORDS_PAGE_ID}/children":
            return {"results": [] if self.hide_created else [
                {"id": page_id, "type": "child_page", "child_page": {"title": page["title"]}}
                for page_id, page in self.pages.items()
            ], "has_more": False}
        if method == "POST" and path == "/pages":
            page_id = f"11111111-1111-1111-1111-{len(self.pages) + 1:012d}"
            self.pages[page_id] = {
                "id": page_id, "title": body["properties"]["title"]["title"][0]["text"]["content"],
                "parent": body["parent"], "url": "https://app.notion.com/p/" + page_id.replace("-", ""),
            }
            self.blocks[page_id] = [dict(copy.deepcopy(block), id=f"block-{index}")
                                    for index, block in enumerate(body["children"])]
            if self.ambiguous:
                raise AmbiguousWrite()
            return {"id": page_id}
        if method == "GET" and path.startswith("/pages/"):
            return copy.deepcopy(self.pages[path.split("/")[-1]])
        if method == "GET" and path.endswith("/children"):
            result = copy.deepcopy(self.blocks[path.split("/")[-2]])
            if self.corrupt_readback:
                result[-1]["paragraph"]["rich_text"][0]["text"]["content"] = 'state\n"tampered"'
            return {"results": result, "has_more": False}
        if method == "PATCH" and path.startswith("/blocks/"):
            for blocks in self.blocks.values():
                for block in blocks:
                    if block["id"] == path.split("/")[-1]:
                        block["paragraph"] = copy.deepcopy(body["paragraph"])
                        return block
        raise AssertionError((method, path))


class EvidenceTests(unittest.TestCase):
    def test_preserves_failed_ci_and_literal_user_input(self):
        report = evidence()
        self.assertEqual(report["test_results"][0]["conclusion"], "failure")
        self.assertEqual(report["test_results"][0]["run_attempt"], 2)
        self.assertIn("$(touch", report["summary"]["title"])
        self.assertEqual(report["test_commands"], [])
        self.assertEqual(report["review_status"], "PENDING_REVIEW")

    def test_collects_all_file_pages(self):
        fixture = GitHubFixture()
        fixture.files *= 101
        fixture.pr["changed_files"] = 101
        report = GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(1, 9)
        self.assertEqual(len(report["changed_files"]), 101)

    def test_rejects_stale_ci(self):
        fixture = GitHubFixture()
        fixture.run["head_sha"] = "e" * 40
        with self.assertRaisesRegex(AutomationError, "Stale CI"):
            GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(1, 9)

    def test_rejects_head_change_during_collection(self):
        fixture = GitHubFixture()
        fixture.change_on_second_read = True
        with self.assertRaisesRegex(AutomationError, "changed during"):
            GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(1, 9)

    def test_rejects_incomplete_files(self):
        fixture = GitHubFixture()
        fixture.pr["changed_files"] = 2
        with self.assertRaisesRegex(AutomationError, "file count"):
            GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(1, 9)

    def test_run_without_pr_uses_commit_association(self):
        fixture = GitHubFixture()
        fixture.run["pull_requests"] = []
        self.assertEqual(GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(run_id=9)["pr_number"], 1)

    def test_push_merge_run_records_merge_sha(self):
        fixture = GitHubFixture()
        fixture.run.update(event="push", head_sha=MERGE, pull_requests=[])
        fixture.pr.update(merged=True, state="closed")
        report = GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(run_id=9)
        self.assertEqual(report["merge_sha"], MERGE)
        self.assertEqual(report["head_sha"], HEAD)
        self.assertEqual(report["test_results"][0]["head_sha"], MERGE)

    def test_merged_pr_without_merge_sha_reports_schema_error(self):
        fixture = GitHubFixture()
        fixture.pr.update(merged=True, state="closed")
        fixture.pr.pop("merge_commit_sha")
        with self.assertRaisesRegex(AutomationError, "API version/schema"):
            GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(1, 9)

    def test_bootstrap_run_has_no_matching_pr(self):
        fixture = GitHubFixture()
        fixture.run["pull_requests"] = []
        fixture.associations = []
        with self.assertRaises(NoMatchingPR):
            GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(run_id=9)

    def test_rejects_different_workflow(self):
        fixture = GitHubFixture()
        fixture.path = ".github/workflows/untrusted.yml"
        with self.assertRaisesRegex(AutomationError, "approved CI"):
            GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(1, 9)

    def test_event_attempt_uses_immutable_attempt_endpoint(self):
        fixture = GitHubFixture()
        report = GitHub(fixture, "Ryu-Jemu/Agent_Kakao").collect(1, 9, 2)
        self.assertEqual(report["test_results"][0]["run_attempt"], 2)
        self.assertIn(("GET", "/repos/Ryu-Jemu/Agent_Kakao/actions/runs/9/attempts/2"), fixture.calls)


class NotionTests(unittest.TestCase):
    def test_create_readback_and_rerun_do_not_duplicate(self):
        fixture = NotionFixture()
        writer = Notion(fixture, RECORDS_PAGE_ID, sleep=lambda _: None)
        report = evidence()
        self.assertTrue(writer.publish(report)["readback_verified"])
        self.assertEqual(writer.publish(report)["status"], "unchanged")
        self.assertEqual(len(fixture.pages), 1)
        self.assertEqual(sum(method == "POST" for method, _, _ in fixture.calls), 1)

    def test_new_ci_observation_updates_existing_page(self):
        fixture = NotionFixture()
        writer = Notion(fixture, RECORDS_PAGE_ID)
        report = evidence()
        writer.publish(report)
        report["test_results"][0]["conclusion"] = "success"
        report["updated_at"] = "2026-10-27T00:00:00Z"
        self.assertEqual(writer.publish(report)["status"], "updated")
        self.assertEqual(len(fixture.pages), 1)

    def test_ci_run_attempt_history_survives_later_publication(self):
        fixture = NotionFixture()
        writer = Notion(fixture, RECORDS_PAGE_ID)
        report = evidence()
        writer.publish(report)
        report["test_results"][0].update(run_attempt=3, conclusion="success")
        writer.publish(report)
        blocks = next(iter(fixture.blocks.values()))
        history = json.loads(block_text(blocks[FIELDS.index("test_results") + 1]).split("\n", 1)[1])
        self.assertEqual([item["run_attempt"] for item in history], [2, 3])
        self.assertEqual(history[0]["conclusion"], "failure")

    def test_renamed_record_is_found_by_marker(self):
        fixture = NotionFixture()
        writer = Notion(fixture, RECORDS_PAGE_ID)
        report = evidence()
        writer.publish(report)
        next(iter(fixture.pages.values()))["title"] = "Human readable new title"
        writer.publish(report)
        self.assertEqual(sum(method == "POST" for method, _, _ in fixture.calls), 1)

    def test_invalid_container_fails_before_network(self):
        fixture = NotionFixture()
        with self.assertRaisesRegex(AutomationError, "outside"):
            Notion(fixture, PROJECT_PAGE_ID)
        self.assertEqual(fixture.calls, [])

    def test_moved_container_blocks_every_write(self):
        fixture = NotionFixture()
        fixture.parent = "e" * 32
        with self.assertRaisesRegex(AutomationError, "approved project"):
            Notion(fixture, RECORDS_PAGE_ID).publish(evidence())
        self.assertFalse(any(method != "GET" for method, _, _ in fixture.calls))

    def test_ambiguous_create_reconciles_without_second_post(self):
        fixture = NotionFixture()
        fixture.ambiguous = True
        result = Notion(fixture, RECORDS_PAGE_ID, sleep=lambda _: None).publish(evidence())
        self.assertEqual(result["status"], "reconciled")
        self.assertEqual(sum(method == "POST" for method, _, _ in fixture.calls), 1)

    def test_unknown_create_stops_without_second_post(self):
        fixture = NotionFixture()
        fixture.ambiguous = True
        fixture.hide_created = True
        with self.assertRaisesRegex(AutomationError, "No duplicate POST"):
            Notion(fixture, RECORDS_PAGE_ID, sleep=lambda _: None).publish(evidence())
        self.assertEqual(sum(method == "POST" for method, _, _ in fixture.calls), 1)

    def test_existing_record_moved_outside_container_is_not_updated(self):
        fixture = NotionFixture()
        writer = Notion(fixture, RECORDS_PAGE_ID)
        writer.publish(evidence())
        next(iter(fixture.pages.values()))["parent"]["page_id"] = PROJECT_PAGE_ID
        with self.assertRaisesRegex(AutomationError, "outside"):
            writer.publish(evidence())
        self.assertFalse(any(method == "PATCH" for method, _, _ in fixture.calls))

    def test_readback_mismatch_is_not_success(self):
        fixture = NotionFixture()
        fixture.corrupt_readback = True
        with self.assertRaisesRegex(AutomationError, "read-back differs"):
            Notion(fixture, RECORDS_PAGE_ID).publish(evidence())

    def test_truncation_is_explicit_and_text_chunks_are_bounded(self):
        report = evidence()
        report["summary"]["title"] = "가" * 15000
        blocks = render(report)
        self.assertIn("TRUNCATED", block_text(blocks[FIELDS.index("summary") + 1]))
        self.assertTrue(all(len(item["text"]["content"]) <= 1900
                            for block in blocks for item in block["paragraph"]["rich_text"]))


class FakeOpener:
    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return io.BytesIO(b'{"ok": true}')


def http_error(status, body=None, headers=None):
    return urllib.error.HTTPError("https://api.example.test/test", status, "error", headers or {},
                                  io.BytesIO(json.dumps(body or {}).encode()))


class TransportAndCliTests(unittest.TestCase):
    def test_cli_collects_merged_pr_using_compatible_http_schema(self):
        fixture = GitHubFixture()
        fixture.pr.update(merged=True, state="closed")
        fixture.run.update(event="push", head_sha=MERGE, pull_requests=[])

        class VersionedGitHub:
            def open(self, request, timeout):
                url = urlsplit(request.full_url)
                response = fixture.request(request.method, url.path + "?" + url.query)
                # The live 2026 API omits this field; test the actual CLI ->
                # transport -> collector path instead of a version assertion.
                if isinstance(response, dict) and request.get_header("X-github-api-version") != "2022-11-28":
                    response.pop("merge_commit_sha", None)
                return io.BytesIO(json.dumps(response).encode())

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            with patch.dict(os.environ, {"GITHUB_TOKEN": "test", "GITHUB_REPOSITORY": "Ryu-Jemu/Agent_Kakao"}), \
                    patch("urllib.request.build_opener", return_value=VersionedGitHub()), \
                    patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["collect", "--run-id", "9", "--output", str(output)]), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["merge_sha"], MERGE)
            self.assertEqual(report["test_results"][0]["head_sha"], MERGE)

    def test_rate_limit_uses_retry_after(self):
        pauses = []
        opener = FakeOpener([http_error(429, headers={"Retry-After": "3"})])
        client = JsonClient("https://api.example.test", "sensitive", opener=opener, sleep=pauses.append)
        self.assertTrue(client.request("GET", "/test")["ok"])
        self.assertEqual(pauses, [3])

    def test_create_503_does_not_blindly_retry(self):
        opener = FakeOpener([http_error(503)])
        with self.assertRaises(AmbiguousWrite):
            JsonClient("https://api.example.test", "secret", opener=opener).request("POST", "/pages", {})
        self.assertEqual(opener.calls, 1)

    def test_unauthorized_is_not_retried_or_leaked(self):
        opener = FakeOpener([http_error(401, {"message": "secret-token"})])
        with self.assertRaises(ApiError) as result:
            JsonClient("https://api.example.test", "secret-token", opener=opener).request("GET", "/test")
        self.assertNotIn("secret-token", str(result.exception))
        self.assertEqual(opener.calls, 1)

    def test_json_dry_run_needs_no_token_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "evidence.json"
            source.write_text(json.dumps(evidence()))
            with patch.dict(os.environ, {}, clear=True), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(main(["publish", "--input", str(source), "--dry-run"]), 0)
                self.assertFalse(json.loads(output.getvalue())["notion_write"])

    def test_known_tokens_are_redacted_recursively(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "my-runtime-secret"}):
            self.assertEqual(sanitize({"items": ["my-runtime-secret", "ghp_" + "A" * 30]}),
                             {"items": ["[REDACTED]", "[REDACTED]"]})

    def test_event_file_pins_run_attempt_for_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            event.write_text(json.dumps({"workflow_run": {"id": 9, "run_attempt": 2}}))
            with patch.dict(os.environ, {"GITHUB_TOKEN": "test", "GITHUB_REPOSITORY": "Ryu-Jemu/Agent_Kakao"}), \
                    patch("automation.cli.GitHub.collect", return_value=evidence()) as collect, \
                    patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["collect", "--event-file", str(event), "--output", str(Path(directory) / "out.json")]), 0)
                collect.assert_called_once_with(None, 9, 2)


if __name__ == "__main__":
    unittest.main()
