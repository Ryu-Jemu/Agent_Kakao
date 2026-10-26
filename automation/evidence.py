"""Collect evidence only through GitHub APIs; never execute repository input."""

import datetime as dt
import re
from urllib.parse import urlencode

from .http import AutomationError

REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SHA = re.compile(r"[a-fA-F0-9]{40}\Z")
CI_PATH = ".github/workflows/ci.yml"


class NoMatchingPR(AutomationError):
    """A CI run (for example repository bootstrap) has no PR to document."""


class GitHub:
    def __init__(self, client, repository):
        if not REPOSITORY.fullmatch(repository):
            raise AutomationError("Invalid GITHUB_REPOSITORY")
        self.client = client
        self.repository = repository
        self.base = f"/repos/{repository}"

    def get(self, suffix):
        return self.client.request("GET", self.base + suffix)

    def pages(self, suffix, *, key=None, max_pages=100):
        result = []
        for page in range(1, max_pages + 1):
            separator = "&" if "?" in suffix else "?"
            body = self.get(suffix + separator + urlencode({"per_page": 100, "page": page}))
            batch = body[key] if key else body
            if not isinstance(batch, list):
                raise AutomationError("Unexpected GitHub pagination response")
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise AutomationError("GitHub pagination limit reached; evidence may be incomplete")

    def resolve_pr(self, run):
        prs = run.get("pull_requests") or []
        if not prs:
            sha = run.get("head_sha", "")
            if not SHA.fullmatch(sha):
                raise AutomationError("Workflow run has an invalid head SHA")
            prs = self.pages(f"/commits/{sha}/pulls")
        numbers = {
            item["number"] for item in prs
            if item.get("base", {}).get("repo", {}).get("id") == run["repository"]["id"]
        }
        if not numbers:
            raise NoMatchingPR("CI run has no associated PR; no Notion write required")
        if len(numbers) != 1:
            raise AutomationError("Cannot uniquely associate this run with a PR; use --pr")
        return numbers.pop()

    def collect(self, pr_number=None, run_id=None, run_attempt=None):
        if run_id is not None and (type(run_id) is not int or run_id <= 0):
            raise AutomationError("Run ID must be a positive integer")
        if run_attempt is not None and (type(run_attempt) is not int or run_attempt <= 0 or run_id is None):
            raise AutomationError("Run attempt requires a valid run ID and positive attempt")
        suffix = f"/actions/runs/{run_id}"
        if run_attempt is not None:
            suffix += f"/attempts/{run_attempt}"
        run = self.get(suffix) if run_id else None
        if run and run_attempt is not None and run.get("run_attempt") != run_attempt:
            raise AutomationError("API returned a different workflow run attempt")
        if run and run.get("repository", {}).get("full_name", "").lower() != self.repository.lower():
            raise AutomationError("Workflow run repository mismatch")
        if run:
            workflow = self.get(f"/actions/workflows/{run['workflow_id']}")
            if workflow.get("path") != CI_PATH or run.get("event") not in ("pull_request", "push", "merge_group"):
                raise AutomationError("Run is not an approved CI workflow/event")
        if pr_number is None:
            if run is None:
                raise AutomationError("Provide --pr or --run-id")
            pr_number = self.resolve_pr(run)
        if not isinstance(pr_number, int) or pr_number <= 0:
            raise AutomationError("PR number must be a positive integer")
        pr = self.get(f"/pulls/{pr_number}")
        base_repo = pr["base"]["repo"]
        if base_repo["full_name"].lower() != self.repository.lower():
            raise AutomationError("PR repository mismatch")
        sha = pr["head"]["sha"]
        if not SHA.fullmatch(sha):
            raise AutomationError("PR head SHA is invalid")
        if pr.get("merged") and not SHA.fullmatch(pr.get("merge_commit_sha") or ""):
            raise AutomationError("Merged PR has no valid merge_commit_sha; verify GitHub API version/schema")
        allowed_shas = {sha}
        if pr.get("merge_commit_sha") and (pr.get("merged") or (run and run.get("event") == "pull_request")):
            allowed_shas.add(pr["merge_commit_sha"])
        if run and run.get("head_sha") not in allowed_shas:
            raise AutomationError("Stale CI run: PR head changed; refusing to attach current files to old evidence")
        if run and run.get("event") == "pull_request":
            associated = {item["number"] for item in run.get("pull_requests", [])}
            if associated and pr_number not in associated:
                raise AutomationError("Workflow run belongs to a different PR")
        files = self.pages(f"/pulls/{pr_number}/files", max_pages=31)
        if len(files) != pr["changed_files"]:
            raise AutomationError("Changed-file count mismatch; incomplete or concurrently modified PR")
        commits = self.pages(f"/pulls/{pr_number}/commits")
        if len(commits) != pr["commits"]:
            raise AutomationError("Commit count mismatch; incomplete or concurrently modified PR")
        runs = [run] if run else self.pages(
            "/actions/runs?" + urlencode({"head_sha": sha}), key="workflow_runs", max_pages=10
        )
        runs = [item for item in runs if item.get("event") in ("pull_request", "push", "merge_group")]
        observations = []
        for item in runs:
            if item.get("head_sha") not in allowed_shas:
                continue
            if not run and self.get(f"/actions/workflows/{item['workflow_id']}").get("path") != CI_PATH:
                continue
            attempt = item.get("run_attempt", 1)
            jobs = self.pages(f"/actions/runs/{item['id']}/attempts/{attempt}/jobs", key="jobs")
            observations.append({
                "run_id": item["id"], "run_attempt": attempt,
                "workflow_id": item["workflow_id"], "name": item["name"],
                "event": item["event"], "head_sha": item["head_sha"],
                "tested_sha": None,
                "status": item["status"], "conclusion": item.get("conclusion"),
                "url": item["html_url"],
                "jobs": [{
                    "id": job["id"], "name": job["name"], "status": job["status"],
                    "conclusion": job.get("conclusion"), "url": job["html_url"],
                    "steps": [{"name": step["name"], "number": step["number"],
                               "status": step["status"], "conclusion": step.get("conclusion")}
                              for step in job.get("steps", [])],
                } for job in jobs],
            })
        # Re-read after collecting every mutable PR endpoint: a synchronize during
        # collection must not label files from a new commit with an old SHA.
        final = self.get(f"/pulls/{pr_number}")
        if final["head"]["sha"] != sha or final["base"]["sha"] != pr["base"]["sha"]:
            raise AutomationError("PR changed during collection; rerun for the new revision")
        if final.get("merged") and not SHA.fullmatch(final.get("merge_commit_sha") or ""):
            raise AutomationError("Merged PR has no valid merge_commit_sha; verify GitHub API version/schema")
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        return {
            "schema_version": 1,
            "record_key": f"{base_repo['id']}:{pr_number}:{sha}",
            "repository": self.repository, "repository_id": base_repo["id"],
            "task_id": None, "pr_number": pr_number, "pr_url": pr["html_url"],
            "base_branch": pr["base"]["ref"], "base_sha": pr["base"]["sha"],
            "head_sha": sha, "tested_sha": None,
            "merge_sha": final.get("merge_commit_sha") if final.get("merged") else None,
            "author": pr["user"]["login"], "implementation_agent": "unverified",
            "changed_files": [{key: item.get(key) for key in
                               ("filename", "status", "additions", "deletions", "changes", "sha", "blob_url")}
                              for item in files],
            "commits": [{"sha": item["sha"], "url": item["html_url"]} for item in commits],
            "summary": {"title": pr["title"], "file_count": len(files), "commit_count": len(commits)},
            "test_commands": [], "test_results": observations,
            "ci_status": "observed" if observations else "not_found",
            "workflow_run_url": observations[0]["url"] if observations else None,
            "known_issues": ["Job/step conclusions are CI observations, not proof of individual test coverage.",
                             "Executed test commands and checkout SHA are not inferred from job names.",
                             "Task ID and implementation agent require a reviewed work contract."],
            "risks": [], "evidence_links": [pr["html_url"], *[item["url"] for item in observations]],
            "review_status": "PENDING_REVIEW", "next_actions": ["Compare evidence with acceptance criteria; request user approval before merge/deploy."],
            "created_at": now, "updated_at": now, "pr_updated_at": final["updated_at"],
            "merged": bool(final.get("merged")), "state": final["state"],
        }
