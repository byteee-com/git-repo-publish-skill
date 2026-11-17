#!/usr/bin/env python3
"""Configure and first-publish reviewed commits to Codeup central edition over HTTPS."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from github_publish import (Stop, clean_env, git, git_root, local_commit, matching,
                            project_root, save_journal, verify_or_push)


HOST = "codeup.aliyun.com"
API = "https://openapi-rdc.aliyuncs.com/oapi/v1/codeup/organizations/"
SEGMENT = r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}"
PROFILE_KEYS = {"organization_id", "namespace", "username", "token_env"}


def repository_path(value):
    parts = value.split("/")
    for part in parts:
        matching(part, SEGMENT, "Codeup path segment")
        if part in (".", "..") or part.endswith(".git"):
            raise Stop("Use a Codeup path without dot segments or .git suffixes.")
    return value


def resolve_target(value, namespace):
    if value.startswith("https://"):
        url = urlsplit(value)
        if url.netloc.lower() != HOST or url.query or url.fragment:
            raise Stop("Use a codeup.aliyun.com URL without credentials, query or fragment.")
        value = url.path.lstrip("/").rstrip("/")
    elif value.startswith("git@"):
        host, sep, value = value[4:].partition(":")
        if not sep or host != HOST:
            raise Stop("Use a codeup.aliyun.com clone address.")
    if value.endswith(".git"):
        value = value[:-4]
    if "/" not in value:
        value = namespace + "/" + value
    repository_path(value)
    if value.rpartition("/")[0] != namespace:
        raise Stop("The target parent path differs from the configured namespace. Select another profile.")
    return value


def validate_profile(profile):
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS:
        raise Stop("Invalid Codeup profile. Run configure with organization, namespace and clone username.")
    matching(profile["organization_id"], r"[A-Za-z0-9_-]{1,100}", "organization ID")
    repository_path(profile["namespace"])
    matching(profile["username"], r"[^\s=\x00-\x1f\x7f]{1,256}", "HTTPS clone username")
    matching(profile["token_env"], r"[A-Za-z_][A-Za-z0-9_]*", "token environment variable name")
    return profile


def read_config(path):
    if not path.exists():
        return {"version": 1, "profiles": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("profiles"), dict):
        raise Stop("Invalid Codeup configuration file.")
    for name, profile in data["profiles"].items():
        matching(name, r"[A-Za-z0-9_-]{1,64}", "profile name")
        validate_profile(profile)
    return data


def token_from_env(name):
    token = os.environ.get(name, "")
    if not token or not token.isascii() or any(c.isspace() or ord(c) < 33 for c in token):
        raise Stop(f"Set {name} to a valid Codeup personal access token in your terminal.")
    return token


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class APIError(Stop):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Codeup API HTTP {status}. Check token permissions, organization and connectivity.")


class Codeup:
    def __init__(self, profile):
        self.profile = validate_profile(profile)
        self.token = token_from_env(profile["token_env"])
        self.base = API + quote(profile["organization_id"], safe="") + "/"
        self.opener = build_opener(NoRedirect())

    def api(self, path, method="GET", body=None):
        request = Request(self.base + path, method=method,
                          headers={"x-yunxiao-token": self.token, "Content-Type": "application/json"},
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.opener.open(request, timeout=45) as response:
                result = json.load(response)
        except HTTPError as error:
            error.close()
            raise APIError(error.code) from None
        except (URLError, TimeoutError):
            raise Stop("Codeup API request failed or timed out. Inspect before retrying a mutation.") from None
        except ValueError:
            raise Stop("Codeup API returned invalid JSON.") from None
        if not isinstance(result, dict) or "errorCode" in result:
            raise Stop("Codeup API returned an unexpected response.")
        return result

    def namespace_id(self):
        result = self.api("namespaces/" + quote(self.profile["namespace"], safe=""))
        path = result.get("fullPath") or result.get("pathWithNamespace")
        if path != self.profile["namespace"] or not isinstance(result.get("id"), int) or result["id"] < 1:
            raise Stop("Codeup returned a different namespace or invalid namespace ID.")
        return result["id"]

    def repo(self, target):
        try:
            result = self.api("repositories/" + quote(target, safe=""))
        except APIError as error:
            if error.status == 404:
                return None
            raise
        if result.get("pathWithNamespace") != target or not isinstance(result.get("id"), int) or result["id"] < 1:
            raise Stop("Codeup returned a different repository or invalid repository ID.")
        return result


class Transport:
    def __init__(self, root, profile, target):
        self.root = root
        self.url = f"https://{HOST}/{target}.git"
        self.env = clean_env()
        self.env[profile["token_env"]] = token_from_env(profile["token_env"])
        self.env.update(GIT_ALLOW_PROTOCOL="https", GIT_ASKPASS="/usr/bin/false")
        self.remote = "publish-" + uuid4().hex
        helper = "!" + shlex.join([sys.executable, str(Path(__file__).resolve()), "_credential",
                                   profile["username"], profile["token_env"], target])
        self.opts = ["-c", "push.followTags=false", "-c", "push.recurseSubmodules=no",
                     "-c", "credential.helper=", "-c", "credential.helper=" + helper,
                     "-c", "credential.interactive=false", "-c", "credential.useHttpPath=true",
                     "-c", f"credential.https://{HOST}.username={profile['username']}",
                     "-c", "http.followRedirects=false", "-c", "http.sslVerify=true",
                     "-c", f"remote.{self.remote}.url={self.url}",
                     "-c", f"remote.{self.remote}.pushurl={self.url}"]
        # URL-specific http settings override general command-scope options.
        for key in ("extraHeader", "cookieFile", "sslVerify", "followRedirects"):
            setting = git(root, "config", "--get-urlmatch", "http." + key, self.url, check=False)
            value = setting.stdout.strip().lower()
            if setting.returncode not in (0, 1) or (setting.returncode == 0 and value and (
                key in {"extraHeader", "cookieFile"}
                or (key == "sslVerify" and value not in {"true", "yes", "on", "1"})
                or (key == "followRedirects" and value not in {"false", "no", "off", "0"})
            )):
                raise Stop(f"Review the effective http.{key} Git setting before publishing.")
        if self.call("ls-remote", "--get-url", "--", self.remote).stdout.splitlines() != [self.url]:
            raise Stop("Git URL rewriting changes the reviewed destination.")

    def call(self, *args, **kwargs):
        return git(self.root, *self.opts, *args, env=self.env, **kwargs)

    def refs(self):
        refs = {}
        for line in self.call("ls-remote", "--refs", "--", self.remote).stdout.splitlines():
            sha, sep, ref = line.partition("\t")
            if not sep or not re.fullmatch(r"[0-9a-f]{40}", sha) or not ref.startswith("refs/"):
                raise Stop("Codeup returned an invalid Git ref.")
            refs[ref] = sha
        return refs


def credential(username, token_env, target, operation):
    if operation != "get":
        return
    fields = dict(line.split("=", 1) for line in sys.stdin.read().splitlines() if "=" in line)
    if (fields.get("protocol") != "https" or fields.get("host") != HOST
        or fields.get("path") not in (target, target + ".git")
        or fields.get("username", username) != username):
        return
    print(f"username={username}\npassword={token_from_env(token_env)}\n")


def require_repo(repo, plan, repo_id):
    if (not repo or repo.get("id") != repo_id or repo.get("visibility") != plan.visibility
        or repo.get("archived") or repo.get("allowPush") is not True):
        raise Stop("Repository identity, visibility or push permission differs from the reviewed plan.")


def metadata_changes(repo, desired):
    changes = {}
    description = desired.get("description")
    if description and (repo.get("description") or "") != description:
        if repo.get("description"):
            raise Stop("Codeup already has a different description. Review it before changing metadata.")
        changes["description"] = description
    existing = {tag["tagName"] for tag in repo.get("repositoryTags", [])}
    wanted = set(desired.get("repositoryTags", []))
    if wanted - existing:
        changes["repositoryTags"] = sorted(existing | wanted)
    return changes


@contextmanager
def locked_journal(root, organization_id, target):
    if git_root(root) != root:
        raise Stop("Run from the reviewed Git repository root.")
    common = git(root, "rev-parse", "--git-common-dir").stdout.strip()
    directory = (root / common).resolve() / "codeup-repo-publish"
    directory.mkdir(mode=0o700, exist_ok=True)
    key = hashlib.sha256((organization_id + "/" + target).encode()).hexdigest()
    with (directory / (key + ".lock")).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop("Another publication for this destination is running.") from None
        yield directory / (key + ".json")


def run_publication(state, journal, api, transport, report, adopted_id=None):
    plan = argparse.Namespace(**state["plan"])
    target = plan.target
    ops = state["operations"]
    report.update(plan=state["plan"], operations=ops, recovery_record=str(journal))
    if api.namespace_id() != plan.namespace_id:
        raise Stop("The configured namespace ID changed. Review the destination.")
    repo = api.repo(target)
    repo_id = state["repository_id"]
    if repo_id is not None:
        if adopted_id is not None:
            raise Stop("The publication already has a verified repository ID.")
        require_repo(repo, plan, repo_id)
    elif repo is not None:
        if ops["repository"] != "requested" or adopted_id is None:
            raise Stop("The repository exists. Inspect and explicitly select its ID before resuming.")
        require_repo(repo, plan, adopted_id)
        if transport.refs():
            raise Stop("Recovery requires an empty repository.")
        repo_id = adopted_id
    else:
        if adopted_id is not None or ops["repository"] == "verified":
            raise Stop("The reviewed repository could not be verified.")
        local_commit(plan)
        ops["repository"] = "requested"
        save_journal(journal, state)
        created = api.api("repositories", "POST", {
            "name": target.rsplit("/", 1)[1], "path": target.rsplit("/", 1)[1],
            "namespaceId": plan.namespace_id, "visibility": plan.visibility, "readMeType": "EMPTY",
        })
        if created.get("pathWithNamespace") != target or not isinstance(created.get("id"), int) or created["id"] < 1:
            raise Stop("Codeup did not return the reviewed repository. Inspect before resuming.")
        repo_id = created["id"]
        state["repository_id"] = repo_id
        save_journal(journal, state)
        repo = api.repo(target)
        require_repo(repo, plan, repo_id)
    if ops["repository"] == "pending" and transport.refs():
        raise Stop("First publication requires a repository without any Git refs.")
    metadata_changes(repo, plan.metadata)
    state["repository_id"] = repo_id
    ops["repository"] = "verified"
    save_journal(journal, state)
    verify_or_push(state, journal, plan, transport)
    repo = api.repo(target)
    require_repo(repo, plan, repo_id)
    branch = api.api(f"repositories/{repo_id}/branches/" + quote(plan.branch, safe=""))
    if branch.get("name") != plan.branch or (branch.get("commit") or {}).get("id") != plan.head:
        raise Stop("Codeup API did not verify the pushed branch and SHA. Inspect before resuming.")
    changes = metadata_changes(repo, plan.metadata)
    if ops["metadata"] == "verified" and changes:
        raise Stop("Previously verified metadata changed. Review before continuing.")
    if changes:
        ops["metadata"] = "requested"
        save_journal(journal, state)
        api.api(f"repositories/{repo_id}", "PUT", changes)
        repo = api.repo(target)
        require_repo(repo, plan, repo_id)
        if metadata_changes(repo, plan.metadata):
            raise Stop("Codeup did not return the reviewed metadata. Inspect before resuming.")
    ops["metadata"] = "verified" if plan.metadata else "skipped"
    save_journal(journal, state)
    report.update(stage="verified", repository=repo, branch=plan.branch, commit=plan.head)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 5 and argv[0] == "_credential":
        try:
            credential(*argv[1:])
            return 0
        except Stop:
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure", help="Save non-secret profile settings locally")
    show = commands.add_parser("config", help="Show a profile and token availability; never print the token")
    probe = commands.add_parser("inspect")
    send = commands.add_parser("publish")
    resume = commands.add_parser("resume")
    default_config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "git-repo-publish/codeup.json"
    for command in (configure, show, probe, send, resume):
        command.add_argument("--config", type=Path, default=default_config)
        command.add_argument("--profile", default="default")
    configure.add_argument("--organization-id", required=True)
    configure.add_argument("--namespace", required=True, help="Full parent path, e.g. org-path/team/subteam")
    configure.add_argument("--username", required=True, help="Codeup HTTPS clone account")
    configure.add_argument("--token-env", default="CODEUP_TOKEN")
    for command in (probe, send, resume):
        command.add_argument("--root", default=".")
        command.add_argument("--target", required=True)
    for command in (send, resume):
        command.add_argument("--confirm-target", required=True, help="The exact full path confirmed after preview")
        command.add_argument("--repo-id", type=int)
    send.add_argument("--mode", choices=("create", "existing"), required=True)
    send.add_argument("--visibility", choices=("private", "internal"), default="private")
    send.add_argument("--branch", required=True)
    send.add_argument("--head", required=True)
    send.add_argument("--description")
    send.add_argument("--tag", action="append", default=[])
    args = parser.parse_args(argv)
    report = {"platform": "codeup", "stage": "preflight"}
    try:
        matching(args.profile, r"[A-Za-z0-9_-]{1,64}", "profile name")
        config = read_config(args.config)
        if args.command == "configure":
            profile = validate_profile({key: getattr(args, key) for key in PROFILE_KEYS})
            args.config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            config["profiles"][args.profile] = profile
            save_journal(args.config, config)
            report.update(stage="configured", profile=profile, config=str(args.config))
        else:
            profile = config["profiles"].get(args.profile)
            if profile is None:
                raise Stop("No such Codeup profile. Run configure first; see references/codeup.md.")
            report.update(profile=profile, token_available=bool(os.environ.get(profile["token_env"])))
            if args.command != "config":
                target = resolve_target(args.target, profile["namespace"])
                root = project_root(args.root)
                report.update(target=target, url=f"https://{HOST}/{target}", protocol="https")
                if args.command in ("publish", "resume") and args.confirm_target != target:
                    raise Stop("The confirmed full Codeup path does not match the publication target.")
                api = Codeup(profile)
                transport = Transport(root, profile, target)
                if args.command == "inspect":
                    top = git_root(root)
                    repo = api.repo(target)
                    refs = transport.refs() if repo else None
                    branch = head = None
                    if top:
                        branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip() or None
                        head = git(root, "rev-parse", "--verify", "HEAD^{commit}", check=False).stdout.strip() or None
                    report.update(namespace_id=api.namespace_id(), repository=repo, refs=refs,
                                  destination=("nonempty" if refs else "empty") if repo else "missing_or_hidden",
                                  project={"root": str(root), "git_root": str(top) if top else None,
                                           "branch": branch, "head": head})
                else:
                    with locked_journal(root, profile["organization_id"], target) as journal:
                        if args.command == "resume":
                            if not journal.exists():
                                raise Stop("No recovery record exists for this project and destination.")
                            state = json.loads(journal.read_text(encoding="utf-8"))
                            plan = state["plan"]
                            if (state["version"] != 1 or plan["platform"] != "codeup" or plan["root"] != str(root)
                                or plan["target"] != target or plan["profile"] != profile):
                                raise Stop("Recovery record differs from the current project, target or profile.")
                            local_commit(argparse.Namespace(**plan))
                        else:
                            if journal.exists():
                                raise Stop("This destination has a recovery record. Use resume.")
                            if (args.mode == "existing") != (args.repo_id is not None) or (args.repo_id is not None and args.repo_id < 1):
                                raise Stop("Existing mode requires a positive reviewed repository ID; create mode forbids it.")
                            matching(args.head, r"[0-9a-f]{40}", "reviewed commit SHA")
                            local_commit(args)
                            if args.description and len(args.description) > 65535:
                                raise Stop("Codeup descriptions must not exceed 65535 characters.")
                            if any(not tag.strip() or any(ord(c) < 32 for c in tag) for tag in args.tag):
                                raise Stop("Codeup tags must be nonempty text without control characters.")
                            metadata = {}
                            if args.description:
                                metadata["description"] = args.description
                            if args.tag:
                                metadata["repositoryTags"] = sorted(set(args.tag))
                            plan = {"platform": "codeup", "root": str(root), "target": target,
                                    "profile": profile, "namespace_id": api.namespace_id(), "mode": args.mode,
                                    "visibility": args.visibility, "branch": args.branch, "head": args.head,
                                    "metadata": metadata}
                            state = {"version": 1, "plan": plan, "repository_id": args.repo_id,
                                     "operations": {"repository": "pending", "push": "pending", "metadata": "pending"}}
                        run_publication(state, journal, api, transport, report,
                                        args.repo_id if args.command == "resume" else None)
    except (Stop, ValueError, OSError, KeyError, TypeError) as error:
        # Never print API bodies, HTTP headers, subprocess stderr or credentials.
        report["error"] = str(error) if isinstance(error, Stop) else "Invalid configuration, recovery record or local file state."
        print(json.dumps(report, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
