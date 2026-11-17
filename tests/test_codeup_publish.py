"""Codeup contract tests plus real Git first-push and interrupted-publication checks."""

import argparse
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import codeup_publish as cp


PROFILE = {"organization_id": "org-id", "namespace": "org-path/team/subteam",
           "username": "clone-user", "token_env": "CODEUP_TEST_TOKEN"}
TARGET = PROFILE["namespace"] + "/demo"
SECRET = "test-only-token-not-a-real-credential"


class ProfileTests(unittest.TestCase):
    def invoke(self, argv):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cp.main(argv)
        self.assertNotIn(SECRET, output.getvalue())
        return code, json.loads(output.getvalue())

    def test_configure_and_show_multiple_profiles_without_persisting_token(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {PROFILE["token_env"]: SECRET}):
            config = Path(directory) / "config.json"
            for name in ("work", "other"):
                code, result = self.invoke([
                    "configure", "--config", str(config), "--profile", name,
                    "--organization-id", PROFILE["organization_id"], "--namespace", PROFILE["namespace"],
                    "--username", PROFILE["username"], "--token-env", PROFILE["token_env"]])
                self.assertEqual(code, 0)
                self.assertEqual(result["stage"], "configured")
            self.assertEqual(set(json.loads(config.read_text())["profiles"]), {"work", "other"})
            self.assertNotIn(SECRET, config.read_text())
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            code, result = self.invoke(["config", "--config", str(config), "--profile", "work"])
            self.assertEqual(code, 0)
            self.assertTrue(result["token_available"])

    def test_missing_profile_is_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            code, result = self.invoke(["config", "--config", directory + "/absent.json"])
            self.assertEqual(code, 1)
            self.assertIn("configure", result["error"])

    def test_confirmation_mismatch_stops_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"version": 1, "profiles": {"default": PROFILE}}))
            with patch.object(cp, "Codeup") as api:
                code, result = self.invoke(["resume", "--config", str(config), "--root", directory,
                                            "--target", TARGET, "--confirm-target", "different/demo"])
            self.assertEqual(code, 1)
            self.assertIn("confirmed", result["error"])
            api.assert_not_called()

    def test_target_formats_and_nested_groups(self):
        for value in (TARGET, "demo", f"https://{cp.HOST}/{TARGET}",
                      f"https://{cp.HOST}/{TARGET}.git", f"git@{cp.HOST}:{TARGET}.git"):
            with self.subTest(value=value):
                self.assertEqual(cp.resolve_target(value, PROFILE["namespace"]), TARGET)

    def test_rejects_wrong_hosts_credentials_and_parent_paths(self):
        for value in ("https://evil.example/" + TARGET, "https://token@" + cp.HOST + "/" + TARGET,
                      "org-path/other/demo", "org-path/team/subteam/../demo",
                      TARGET + "?token=secret", "https://" + cp.HOST + "/" + TARGET + "#fragment"):
            with self.subTest(value=value), self.assertRaises(cp.Stop):
                cp.resolve_target(value, PROFILE["namespace"])

    def test_token_is_required_and_not_echoed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(cp.Stop) as error:
            cp.Codeup(PROFILE)
        self.assertIn(PROFILE["token_env"], str(error.exception))

    def test_credential_is_scoped_to_host_path_user_and_get_operation(self):
        fields = f"protocol=https\nhost={cp.HOST}\npath={TARGET}.git\nusername=clone-user\n"
        with patch.dict(os.environ, {PROFILE["token_env"]: SECRET}):
            for data, operation, expected in (
                (fields, "get", True), (fields, "store", False), (fields, "erase", False),
                (fields.replace(cp.HOST, "other.example"), "get", False),
                (fields.replace(TARGET, TARGET + "-other"), "get", False),
                (fields.replace("clone-user", "someone-else"), "get", False),
            ):
                with patch("sys.stdin", io.StringIO(data)), redirect_stdout(io.StringIO()) as output:
                    cp.credential(PROFILE["username"], PROFILE["token_env"], TARGET, operation)
                self.assertEqual(SECRET in output.getvalue(), expected)

    def test_api_encodes_paths_sends_token_header_and_rejects_redirects(self):
        with patch.dict(os.environ, {PROFILE["token_env"]: SECRET}):
            api = cp.Codeup(PROFILE)
        response = io.BytesIO(json.dumps({"id": 12, "pathWithNamespace": TARGET}).encode())
        with patch.object(api.opener, "open", return_value=response) as opening:
            self.assertEqual(api.repo(TARGET)["id"], 12)
        request = opening.call_args.args[0]
        self.assertIn("org-path%2Fteam%2Fsubteam%2Fdemo", request.full_url)
        self.assertEqual(request.get_header("X-yunxiao-token"), SECRET)
        self.assertIsNone(cp.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example"))

    def test_api_404_and_permission_errors_are_distinct_and_sanitized(self):
        with patch.dict(os.environ, {PROFILE["token_env"]: SECRET}):
            api = cp.Codeup(PROFILE)
        for status in (404, 403, 302):
            with patch.object(api.opener, "open", side_effect=HTTPError("hidden", status, SECRET, {}, None)):
                if status == 404:
                    self.assertIsNone(api.repo(TARGET))
                else:
                    with self.assertRaises(cp.APIError) as error:
                        api.repo(TARGET)
                    self.assertNotIn(SECRET, str(error.exception))

    def test_namespace_must_match_exact_path(self):
        with patch.dict(os.environ, {PROFILE["token_env"]: SECRET}):
            api = cp.Codeup(PROFILE)
        with patch.object(api, "api", return_value={"id": 3, "fullPath": "other/team"}):
            with self.assertRaises(cp.Stop):
                api.namespace_id()


class BareTransport:
    """Real Git transport limited to an isolated local bare repository."""
    def __init__(self, root, remote):
        self.root = root
        self.remote = str(remote)
        self.push_count = 0

    def call(self, *args, **kwargs):
        if args[0] == "push":
            self.push_count += 1
        return cp.git(self.root, *args, **kwargs)

    def refs(self):
        result = self.call("ls-remote", "--refs", self.remote)
        return dict((ref, sha) for sha, ref in (row.split("\t") for row in result.stdout.splitlines()))


class FakeCodeup:
    def __init__(self, transport, head):
        self.transport = transport
        self.head = head
        self.repository = None
        self.requests = []
        self.lose_creation_response = False
        self.fail_metadata = False
        self.wrong_branch_sha = False

    def namespace_id(self):
        return 7

    def repo(self, target):
        return copy.deepcopy(self.repository)

    def api(self, path, method="GET", body=None):
        self.requests.append((path, method, body))
        if method == "POST":
            self.repository = {"id": 42, "pathWithNamespace": TARGET, "visibility": "private",
                               "allowPush": True, "archived": False, "repositoryTags": []}
            if self.lose_creation_response:
                raise cp.Stop("Simulated lost creation response")
            return self.repository
        if method == "PUT":
            if self.fail_metadata:
                raise cp.Stop("Simulated metadata failure")
            self.repository.update({key: value for key, value in body.items() if key != "repositoryTags"})
            if "repositoryTags" in body:
                self.repository["repositoryTags"] = [{"tagName": tag} for tag in body["repositoryTags"]]
            return self.repository
        name = path.split("/branches/", 1)[1]
        return {"name": name, "commit": {"id": "f" * 40 if self.wrong_branch_sha else self.head}}


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "project"
        self.root.mkdir()
        self.remote = Path(self.temp.name) / "remote.git"
        self.command("git", "init", "-q", "--initial-branch=main", str(self.root))
        self.command("git", "init", "-q", "--bare", str(self.remote))
        (self.root / "README.md").write_text("A test project\n")
        cp.git(self.root, "add", "README.md")
        cp.git(self.root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "initial")
        self.head = cp.git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.transport = BareTransport(self.root, self.remote)
        self.api = FakeCodeup(self.transport, self.head)
        self.journal = Path(self.temp.name) / "journal.json"
        self.state = {"version": 1, "repository_id": None,
                      "plan": {"platform": "codeup", "root": str(self.root), "target": TARGET, "profile": PROFILE,
                               "namespace_id": 7, "mode": "create", "visibility": "private",
                               "branch": "main", "head": self.head,
                               "metadata": {"description": "A project", "repositoryTags": ["工具", "Python"]}},
                      "operations": {"repository": "pending", "push": "pending", "metadata": "pending"}}

    def command(self, *argv):
        subprocess.run(argv, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def publish(self, adopted_id=None):
        result = {}
        cp.run_publication(self.state, self.journal, self.api, self.transport, result, adopted_id)
        return result

    def create_existing(self):
        self.api.api("repositories", "POST", {})
        self.state["plan"]["mode"] = "existing"
        self.state["repository_id"] = 42

    def test_first_publish_creates_only_reviewed_branch_and_verifies_metadata(self):
        result = self.publish()
        self.assertEqual(result["stage"], "verified")
        self.assertEqual(self.transport.refs(), {"refs/heads/main": self.head})
        body = self.api.requests[0][2]
        self.assertEqual(body["namespaceId"], 7)
        self.assertEqual(body["readMeType"], "EMPTY")
        self.assertNotIn("templateProject", body)
        self.assertEqual(self.state["operations"], dict.fromkeys(("repository", "push", "metadata"), "verified"))
        self.assertNotIn(SECRET, self.journal.read_text())
        self.assertEqual(cp.git(self.root, "remote").stdout, "")

    def test_complete_resume_is_read_only(self):
        self.publish()
        self.api.requests.clear()
        self.publish()
        self.assertEqual(self.transport.push_count, 1)
        self.assertTrue(all(method == "GET" for _, method, _ in self.api.requests))

    def test_reuses_explicit_empty_repository(self):
        self.create_existing()
        self.api.requests.clear()
        self.publish()
        self.assertFalse(any(method == "POST" for _, method, _ in self.api.requests))

    def test_nonempty_repository_is_not_pushed(self):
        self.create_existing()
        cp.git(self.root, "push", str(self.remote), "HEAD:refs/heads/other")
        with self.assertRaises(cp.Stop):
            self.publish()
        self.assertEqual(self.transport.push_count, 0)
        self.assertEqual(self.transport.refs(), {"refs/heads/other": self.head})

    def test_unselected_existing_repository_stops(self):
        self.api.api("repositories", "POST", {})
        with self.assertRaises(cp.Stop):
            self.publish()
        self.assertEqual(self.transport.push_count, 0)

    def test_changed_identity_visibility_permission_or_namespace_stops(self):
        for field, value in (("id", 43), ("visibility", "internal"), ("allowPush", False), ("archived", True)):
            self.create_existing()
            self.api.repository[field] = value
            with self.subTest(field=field), self.assertRaises(cp.Stop):
                self.publish()
        with patch.object(self.api, "namespace_id", return_value=8), self.assertRaises(cp.Stop):
            self.publish()
        self.assertEqual(self.transport.push_count, 0)

    def test_lost_creation_response_needs_explicit_repo_adoption(self):
        self.api.lose_creation_response = True
        with self.assertRaises(cp.Stop):
            self.publish()
        self.assertEqual(json.loads(self.journal.read_text())["operations"]["repository"], "requested")
        with self.assertRaises(cp.Stop):
            self.publish()
        self.publish(adopted_id=42)
        self.assertEqual(sum(method == "POST" for _, method, _ in self.api.requests), 1)

    def test_metadata_failure_resumes_without_another_push(self):
        self.api.fail_metadata = True
        with self.assertRaises(cp.Stop):
            self.publish()
        self.assertEqual(self.state["operations"]["push"], "verified")
        self.api.fail_metadata = False
        self.publish()
        self.assertEqual(self.transport.push_count, 1)

    def test_lost_push_response_resumes_only_the_reviewed_commit(self):
        self.publish()
        self.state["operations"]["push"] = "requested"
        self.publish()
        self.assertEqual(self.transport.push_count, 1)

    def test_unknown_refs_prevent_adopting_an_uncertain_push(self):
        self.publish()
        self.state["operations"]["push"] = "requested"
        cp.git(self.root, "push", str(self.remote), "HEAD:refs/heads/other")
        with self.assertRaises(cp.Stop):
            self.publish()

    def test_api_sha_mismatch_prevents_success_and_metadata_mutation(self):
        self.api.wrong_branch_sha = True
        with self.assertRaises(cp.Stop):
            self.publish()
        self.assertFalse(any(method == "PUT" for _, method, _ in self.api.requests))
        self.api.wrong_branch_sha = False
        self.publish()
        self.assertEqual(self.transport.push_count, 1)

    def test_different_description_stops_before_push_and_tags_are_preserved(self):
        self.create_existing()
        self.api.repository["description"] = "Someone else's description"
        with self.assertRaises(cp.Stop):
            self.publish()
        self.assertEqual(self.transport.push_count, 0)
        self.api.repository["description"] = ""
        self.api.repository["repositoryTags"] = [{"tagName": "Existing"}]
        self.publish()
        self.assertEqual({tag["tagName"] for tag in self.api.repository["repositoryTags"]},
                         {"Existing", "工具", "Python"})

    def test_changed_local_head_stops_before_creating_repository(self):
        self.state["plan"]["head"] = "f" * 40
        with self.assertRaises(cp.Stop):
            self.publish()
        self.assertEqual(self.api.requests, [])

    def test_transport_credentials_work_without_tokens_in_urls_or_arguments(self):
        with patch.dict(os.environ, {PROFILE["token_env"]: SECRET}):
            transport = cp.Transport(self.root, PROFILE, TARGET)
            result = subprocess.run(
                ["git", *transport.opts, "credential", "fill"], cwd=self.root, env=transport.env,
                input=f"protocol=https\nhost={cp.HOST}\npath={TARGET}.git\n\n",
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        self.assertIn("password=" + SECRET, result.stdout)
        self.assertNotIn(SECRET, " ".join(transport.opts))
        self.assertNotIn(SECRET, transport.url)
        self.assertEqual(cp.git(self.root, "remote").stdout, "")

    def test_transport_rejects_url_rewriting_and_unsafe_http_configuration(self):
        with patch.dict(os.environ, {PROFILE["token_env"]: SECRET}):
            cp.git(self.root, "config", "http.https://codeup.aliyun.com/.sslVerify", "false")
            with self.assertRaises(cp.Stop):
                cp.Transport(self.root, PROFILE, TARGET)
            cp.git(self.root, "config", "--unset", "http.https://codeup.aliyun.com/.sslVerify")
            cp.git(self.root, "config", "url.https://evil.example/.insteadOf", "https://codeup.aliyun.com/")
            with self.assertRaises(cp.Stop):
                cp.Transport(self.root, PROFILE, TARGET)

    def test_resume_rejects_changed_profile_before_mutating_remote(self):
        self.publish()
        config = Path(self.temp.name) / "config.json"
        changed = dict(PROFILE, username="other-user")
        config.write_text(json.dumps({"version": 1, "profiles": {"default": changed}}))
        with cp.locked_journal(self.root, PROFILE["organization_id"], TARGET) as journal:
            cp.save_journal(journal, self.state)
        with patch.dict(os.environ, {PROFILE["token_env"]: SECRET}), patch.object(cp, "Codeup") as api, \
                patch.object(cp, "Transport"), redirect_stdout(io.StringIO()) as output:
            result = cp.main(["resume", "--config", str(config), "--root", str(self.root),
                              "--target", TARGET, "--confirm-target", TARGET])
        self.assertEqual(result, 1)
        self.assertIn("profile", json.loads(output.getvalue())["error"])
        api.return_value.api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
