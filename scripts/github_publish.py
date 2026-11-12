#!/usr/bin/env python3
"""Select a stored gh identity and publish one reviewed commit to github.com."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from uuid import uuid4


HOST = "github.com"
LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
REPO = r"[A-Za-z0-9_.-]{1,100}"
OID = r"[0-9a-f]{40}"


class Stop(Exception):
    pass


class APIError(Stop):
    def __init__(self, method, path, status):
        self.status = status
        super().__init__(f"GitHub {method} {path}: HTTP {status or 'unknown'}. "
                         "Check the account, token scope, organization policy/SSO and connectivity.")


def clean_env():
    env = {k: v for k, v in os.environ.items()
           if k not in {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
                        "GH_HOST", "GH_REPO", "GH_DEBUG"}
           and not k.startswith("GIT_")}
    env.update(GH_PROMPT_DISABLED="1", NO_COLOR="1", LC_ALL="C", GIT_TERMINAL_PROMPT="0")
    return env


def run(args, *, env=None, cwd=None, data=None, timeout=45):
    try:
        return subprocess.run(args, cwd=cwd, env=env or clean_env(),
                              input=data if data is not None else "", text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError:
        raise Stop(f"Required command is missing: {args[0]}") from None
    except subprocess.TimeoutExpired:
        raise Stop(f"{Path(args[0]).name} timed out. Recheck remote state before retrying.") from None


def stored_token(account):
    result = run(["gh", "auth", "token", "--hostname", HOST, "--user", account])
    token = result.stdout.strip()
    if result.returncode or not token or any(c.isspace() for c in token):
        raise Stop(f"No usable saved GitHub CLI credential for @{account}. Use gh auth login in your terminal.")
    return token


class Github:
    def __init__(self, account):
        self.account = account
        self.env = dict(clean_env(), GH_TOKEN=stored_token(account))
        if self.api("user").get("login", "").casefold() != account.casefold():
            raise Stop("Stored CLI credential does not authenticate as the selected GitHub account.")

    def api(self, path, method="GET", body=None, paginate=False):
        args = ["gh", "api", "--hostname", HOST, "--method", method, path]
        if body is not None:
            args.extend(["--input", "-"])
        if paginate:
            args.extend(["--paginate", "--slurp"])
        res = run(args, env=self.env, data=json.dumps(body) if body is not None else None)
        if res.returncode:
            match = re.search(r"\(HTTP (\d{3})\)", res.stderr)
            raise APIError(method, path, int(match[1]) if match else None)
        try:
            return json.loads(res.stdout)
        except ValueError:
            raise Stop("GitHub CLI returned an invalid JSON response.") from None

    def repo(self, path, target):
        try:
            result = self.api(path)
        except APIError as e:
            if e.status == 404:
                return None
            raise
        if result.get("full_name", "").casefold() != target.casefold():
            raise Stop("GitHub resolved this address to a different repository. Review the canonical target.")
        return result


def accounts():
    res = run(["gh", "auth", "status", "--hostname", HOST, "--json", "hosts"])
    if res.returncode:
        raise Stop("Cannot list saved accounts. Use a recent gh CLI and run gh auth login --hostname github.com.")
    try:
        rows = json.loads(res.stdout)["hosts"] or {}
        return {"accounts": [
            {"login": row["login"], "active": row.get("active", False),
             "status": row.get("state", "unknown")}
            for row in (rows.get(HOST) or []) if row.get("login")
        ]}
    except (KeyError, TypeError, ValueError):
        raise Stop("GitHub CLI returned an unexpected account listing.") from None


def matching(value, pattern, label):
    if not re.fullmatch(pattern, value or ""):
        raise Stop(f"Invalid {label}.")
    return value


def resolve_target(address, owner=None, name=None, ssh_host=None):
    if address:
        if owner is not None or name is not None:
            raise Stop("Use --target or the --owner and --repo pair.")
        if address.startswith("https://"):
            url = urlsplit(address)
            if url.netloc.lower() != HOST or url.query or url.fragment:
                raise Stop("Use a github.com repository URL without credentials, query or fragment.")
            address = url.path[1:]
            address = address.rstrip("/")
        elif address.startswith("git@"):
            host, sep, address = address[4:].partition(":")
            if not sep or host.lower() not in (HOST, (ssh_host or HOST).lower()):
                raise Stop("Use github.com or the explicitly selected SSH host alias.")
        parts = address.split("/")
        if len(parts) != 2:
            raise Stop("Use a GitHub repository URL or owner/repo.")
        owner, name = parts
        if name.lower().endswith(".git"):
            name = name[:-4]
    matching(owner, LOGIN, "owner")
    matching(name, REPO, "repository name")
    if name in (".", "..") or name.lower().endswith(".git"):
        raise Stop("Provide the repository name without the .git suffix.")
    return owner, name


def git(root, *args, env=None, check=True, timeout=45):
    res = run(["git", *args], cwd=root, env=env, timeout=timeout)
    if check and res.returncode:
        i = 0
        while args[i] == "-c":
            i += 2
        command = args[i]
        if command == "push" and "stale info" in res.stderr.lower():
            raise Stop("The destination branch appeared before the push. Inspect the repository again.")
        if command == "push" and any(
            phrase in res.stderr.lower() for phrase in ("non-fast-forward", "fetch first")
        ):
            raise Stop("Git refused a non-fast-forward push. Recheck the remote branch and reconcile its history.")
        raise Stop(f"Git {command} failed. Check the project Git state, transport access and branch rules.")
    return res


class Transport:
    def __init__(self, root, args, target):
        self.root = root
        self.env = clean_env()
        protocol = args.protocol
        self.env["GIT_ALLOW_PROTOCOL"] = protocol
        opts = ["-c", "push.followTags=false", "-c", "push.recurseSubmodules=no"]
        if protocol == "https":
            if args.ssh_host:
                raise Stop("--ssh-host is only valid with SSH.")
            self.url = f"https://{HOST}/{target}.git"
            self.env["GIT_ASKPASS"] = "/usr/bin/false"
            # Never rely on a cached credential for another GitHub account.
            helper = "!" + shlex.join([sys.executable, str(Path(__file__).resolve()),
                                       "_credential", args.account, target])
            opts += ["-c", "credential.helper=", "-c", f"credential.helper={helper}",
                     "-c", "credential.interactive=false",
                     "-c", f"credential.https://{HOST}.username={args.account}",
                     "-c", "credential.useHttpPath=true",
                     "-c", "http.followRedirects=false", "-c", "http.sslVerify=true"]
            for key in ("extraHeader", "cookieFile", "sslVerify", "followRedirects"):
                custom = git(root, "config", "--get-urlmatch", f"http.{key}", self.url, check=False)
                if custom.returncode not in (0, 1) or (custom.returncode == 0 and custom.stdout.strip()
                    and (key in {"extraHeader", "cookieFile"} or
                         (key == "sslVerify" and custom.stdout.strip().lower() not in {"true", "yes", "on", "1"}) or
                         (key == "followRedirects" and custom.stdout.strip().lower() not in {"false", "no", "off", "0"}))):
                    raise Stop(f"Review the effective http.{key} Git setting before publishing.")
        else:
            alias = matching(args.ssh_host or HOST, r"[A-Za-z0-9][A-Za-z0-9.-]*", "SSH host alias")
            self.url = f"git@{alias}:{target}.git"
            ssh = ["ssh", "-o", f"HostName={HOST}", "-o", f"HostKeyAlias={HOST}",
                   "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                   "-o", "ControlMaster=no", "-o", "ControlPath=none",
                   "-o", "ConnectTimeout=15"]
            result = run([*ssh, "-T", f"git@{alias}"])
            greeting = re.search(r"^Hi ([^!]+)! You've successfully authenticated",
                                 result.stdout + "\n" + result.stderr, re.MULTILINE)
            if result.returncode != 1 or not greeting or greeting[1].casefold() != args.account.casefold():
                actual = f" (authenticated as {greeting[1]})" if greeting else ""
                raise Stop(f"SSH did not authenticate as @{args.account}{actual}. Check the key, alias and trusted host key.")
            self.env.update(GIT_SSH_COMMAND=shlex.join(ssh), GIT_SSH_VARIANT="ssh")

        # Use a process-only remote with an explicit push URL. This avoids
        # remote.*.mirror, multiple URLs and implicit pushInsteadOf routing.
        self.remote = "publish-" + uuid4().hex
        self.opts = [*opts, "-c", f"remote.{self.remote}.url={self.url}",
                     "-c", f"remote.{self.remote}.pushurl={self.url}"]
        # ls-remote sees command-scope remotes on Git versions where
        # remote get-url doesn't. The explicit pushurl ignores pushInsteadOf;
        # the identical fetch and push URLs share the insteadOf rewrite.
        resolved = self.call("ls-remote", "--get-url", "--", self.remote).stdout.splitlines()
        if resolved != [self.url]:
            raise Stop("Git URL rewriting changes the reviewed destination. Review Git config before publishing.")

    def call(self, *args, **kwargs):
        return git(self.root, *self.opts, *args, env=self.env, **kwargs)

    def refs(self):
        res = self.call("ls-remote", "--refs", "--", self.remote)
        refs = {}
        for line in res.stdout.splitlines():
            sha, sep, ref = line.partition("\t")
            if not sep or not re.fullmatch(OID, sha) or not ref.startswith("refs/"):
                raise Stop("Remote returned an unexpected Git ref.")
            refs[ref] = sha
        return refs


def credential(account, target, operation):
    if operation != "get":
        return
    fields = dict(line.split("=", 1) for line in sys.stdin.read().splitlines() if "=" in line)
    path = fields.get("path", "")
    if (fields.get("protocol") != "https" or fields.get("host") != HOST
        or path not in (target, target + ".git")):
        return
    token = stored_token(account)
    print(f"username={account}\npassword={token}\n")


def project_root(path):
    root = Path(path).resolve()
    if not root.is_dir():
        raise Stop("The project directory does not exist.")
    return root


def git_root(root):
    top = git(root, "rev-parse", "--show-toplevel", check=False)
    return Path(top.stdout.strip()).resolve() if top.returncode == 0 else None


def local_commit(args):
    root = project_root(args.root)
    if git_root(root) != root:
        raise Stop("The reviewed project directory is not the Git repository root.")
    ref = "refs/heads/" + args.branch
    git(root, "check-ref-format", ref)
    current = git(root, "symbolic-ref", "-q", "HEAD", check=False)
    commit = git(root, "rev-parse", "--verify", "HEAD^{commit}", check=False)
    if current.returncode or commit.returncode or current.stdout.strip() != ref or commit.stdout.strip() != args.head:
        raise Stop("The current branch or commit differs from the reviewed plan.")
    return root, ref


def repo_summary(repo):
    return {key: repo.get(key) for key in (
        "id", "full_name", "visibility", "archived", "disabled", "default_branch",
        "description", "homepage", "topics", "permissions")}


def require_repo(repo, args, expected_id=None):
    if not repo or repo.get("visibility") != args.visibility or (
        expected_id is not None and repo.get("id") != expected_id
    ) or repo.get("archived") or repo.get("disabled"):
        raise Stop("Repository identity, visibility or writable state differs from the reviewed plan.")
    if not (repo.get("permissions") or {}).get("push"):
        raise Stop("The selected GitHub account does not have verified push access.")


def inspect(args, root, gh, path, target, report):
    top = git_root(root)
    branch, head = None, None
    if top:
        branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip() or None
        head = git(root, "rev-parse", "--verify", "HEAD^{commit}", check=False).stdout.strip() or None
    report["project"] = {"root": str(root), "git_root": str(top) if top else None,
                         "branch": branch, "head": head}
    repo = gh.repo(path, target)
    report["repository"] = repo_summary(repo) if repo else None
    transport = Transport(root, args, target)
    report["clone_url"] = transport.url
    if repo:
        report["refs"] = transport.refs()
        report["destination"] = "nonempty" if report["refs"] else "empty"
    else:
        report["destination"] = "missing_or_hidden"


def publication_plan(args, root):
    if args.mode == "existing":
        if not args.repo_id or args.repo_id < 1 or args.remote_head not in (None, "empty"):
            raise Stop("Existing mode requires the reviewed ID of an empty repository.")
    elif args.repo_id is not None or args.remote_head is not None:
        raise Stop("Create mode does not accept an existing repository ID or branch tip.")
    metadata = {key: value for key, value in (
        ("description", args.description), ("homepage", args.homepage)) if value}
    if args.homepage:
        url = urlsplit(args.homepage)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or any(
            char.isspace() for char in args.homepage
        ):
            raise Stop("Homepage must be an HTTP(S) URL without credentials.")
    if len(args.topic) > 20 or any(not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", t) for t in args.topic):
        raise Stop("Use up to 20 lowercase GitHub topics, each 1–50 characters.")
    if args.topic:
        metadata["topics"] = sorted(set(args.topic))
    matching(args.head, OID, "reviewed commit SHA")
    return {
        "platform": "github", "root": str(root), "account": args.account,
        "owner": args.owner, "repo": args.repo, "mode": args.mode, "repo_id": args.repo_id,
        "visibility": args.visibility, "protocol": args.protocol, "ssh_host": args.ssh_host,
        "branch": args.branch, "head": args.head, "metadata": metadata,
    }


@contextmanager
def locked_journal(root, target):
    if git_root(root) != root:
        raise Stop("The project directory must be the initialized Git repository root.")
    common = git(root, "rev-parse", "--git-common-dir").stdout.strip()
    # Preserve the journal and lock paths used before the skill was renamed.
    directory = (root / common).resolve() / "github-repo-publish"
    directory.mkdir(mode=0o700, exist_ok=True)
    key = hashlib.sha256(target.casefold().encode()).hexdigest()
    with (directory / (key + ".lock")).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop("Another publication for this destination is already running.") from None
        yield directory / (key + ".json")


def save_journal(path, state):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temp:
        temporary = Path(temp.name)
        try:
            json.dump(state, temp, ensure_ascii=False, indent=2)
            temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def load_journal(path, root, target):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        plan = state["plan"]
        if (state["version"] == 1 and plan["platform"] == "github" and plan["root"] == str(root)
            and f"{plan['owner']}/{plan['repo']}".casefold() == target.casefold()):
            return state
    except (KeyError, TypeError, ValueError):
        pass
    raise Stop("The recovery record is invalid or belongs to a different project root.")


def metadata_changes(repo, desired):
    fields = {}
    for key in ("description", "homepage"):
        if key in desired and (repo.get(key) or "") != desired[key]:
            if repo.get(key):
                raise Stop(f"The repository already has a different {key}. Review it before changing metadata.")
            fields[key] = desired[key]
    current = set(repo.get("topics") or [])
    requested = set(desired.get("topics", []))
    if len(current | requested) > 20:
        raise Stop("The reviewed topics plus existing topics exceed the GitHub limit.")
    topics = sorted(current | requested) if requested - current else []
    return fields, topics


def read_destination(gh, path, target, plan, repo_id):
    repo = gh.repo(path, target)
    require_repo(repo, plan, repo_id)
    return repo


def establish_repository(state, journal, gh, path, target, transport, adopted_id):
    plan = argparse.Namespace(**state["plan"])
    operations = state["operations"]
    repo = gh.repo(path, target)
    repo_id = state["repository_id"]

    if repo_id is not None:
        if adopted_id is not None:
            raise Stop("This publication already has a verified repository ID.")
        require_repo(repo, plan, repo_id)
        if operations["repository"] == "pending":
            if transport.refs():
                raise Stop("The destination contains Git refs. First publication requires an empty repository.")
            metadata_changes(repo, plan.metadata)
    elif operations["repository"] == "requested" and repo is not None:
        if adopted_id is None:
            raise Stop("Creation was interrupted. Inspect the destination and explicitly select its ID to resume.")
        require_repo(repo, plan, adopted_id)
        if transport.refs():
            raise Stop("The repository selected for recovery already contains refs.")
        metadata_changes(repo, plan.metadata)
        repo_id = adopted_id
    elif repo is not None:
        raise Stop("The destination already exists. Inspect it and explicitly select it if it is empty.")
    elif adopted_id is not None:
        raise Stop("The selected repository ID could not be verified.")
    else:
        local_commit(plan)
        endpoint = "user/repos" if plan.owner.casefold() == plan.account.casefold() else f"orgs/{plan.owner}/repos"
        operations["repository"] = "requested"
        save_journal(journal, state)
        created = gh.api(endpoint, "POST", {
            "name": plan.repo, "private": plan.visibility == "private", "auto_init": False,
        })
        if created.get("full_name", "").casefold() != target.casefold() or not created.get("id"):
            raise Stop("GitHub did not return the reviewed repository and its ID. Inspect before resuming.")
        repo_id = created["id"]
        state["repository_id"] = repo_id
        save_journal(journal, state)
        repo = read_destination(gh, path, target, plan, repo_id)

    state["repository_id"] = repo_id
    operations["repository"] = "verified"
    save_journal(journal, state)
    return repo


def verify_or_push(state, journal, plan, transport):
    operations = state["operations"]
    ref = "refs/heads/" + plan.branch
    refs = transport.refs()
    if operations["push"] == "verified":
        if refs.get(ref) != plan.head:
            raise Stop("The previously verified remote branch changed. Review it before continuing.")
        return
    if refs == {ref: plan.head} and operations["push"] == "requested":
        operations["push"] = "verified"
        save_journal(journal, state)
        return
    if refs:
        raise Stop("The destination contains Git refs. First publication requires an empty repository.")

    local_commit(plan)
    operations["push"] = "requested"
    save_journal(journal, state)
    # An empty expectation only permits creating the branch. It cannot
    # replace history if the branch appears between ls-remote and push.
    transport.call("push", "--no-follow-tags", "--recurse-submodules=no",
                   f"--force-with-lease={ref}:", "--",
                   transport.remote, f"{plan.head}:{ref}", timeout=300)
    if transport.refs().get(ref) != plan.head:
        raise Stop("Git reported success but the remote commit did not verify. Inspect before resuming.")
    operations["push"] = "verified"
    save_journal(journal, state)


def apply_metadata(state, journal, gh, path, target, plan):
    operations = state["operations"]
    repo_id = state["repository_id"]
    repo = read_destination(gh, path, target, plan, repo_id)
    if not plan.metadata:
        operations["metadata"] = "skipped"
    else:
        fields, topics = metadata_changes(repo, plan.metadata)
        if operations["metadata"] == "verified" and (fields or topics):
            raise Stop("Previously verified metadata has changed. Review the repository before editing.")
        if fields or topics:
            operations["metadata"] = "requested"
            save_journal(journal, state)
            if fields:
                gh.api(path, "PATCH", fields)
                repo = read_destination(gh, path, target, plan, repo_id)
                fields, topics = metadata_changes(repo, plan.metadata)
                if fields:
                    raise Stop("GitHub did not return the reviewed description or homepage.")
            if topics:
                gh.api(path + "/topics", "PUT", {"names": topics})
                repo = read_destination(gh, path, target, plan, repo_id)
            fields, topics = metadata_changes(repo, plan.metadata)
            if fields or topics:
                raise Stop("GitHub did not return all of the reviewed metadata.")
        operations["metadata"] = "verified"
    save_journal(journal, state)
    return repo


def run_publication(state, journal, report, adopted_id=None):
    plan = argparse.Namespace(**state["plan"])
    target = f"{plan.owner}/{plan.repo}"
    path = f"repos/{target}"
    root = Path(plan.root)
    report.pop("stage", None)
    report.update(plan=state["plan"], operations=state["operations"], recovery_record=str(journal),
                  account=plan.account, url=f"https://{HOST}/{target}")
    gh = Github(plan.account)
    transport = Transport(root, plan, target)
    report["clone_url"] = transport.url
    repo = establish_repository(state, journal, gh, path, target, transport, adopted_id)
    report["repository"] = repo_summary(repo)

    if state["operations"]["push"] == "pending":
        metadata_changes(repo, plan.metadata)
    verify_or_push(state, journal, plan, transport)
    repo = apply_metadata(state, journal, gh, path, target, plan)
    report.update(stage="verified", repository=repo_summary(repo), commit=plan.head, branch=plan.branch,
                  url=f"https://{HOST}/{repo['full_name']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("accounts")
    owners = commands.add_parser("owners")
    probe = commands.add_parser("inspect")
    send = commands.add_parser("publish")
    resume = commands.add_parser("resume")
    for command in (owners, probe, send):
        command.add_argument("--account", required=True)
    for command in (probe, send, resume):
        command.add_argument("--target")
        command.add_argument("--owner")
        command.add_argument("--repo")
        command.add_argument("--root", default=".")
        command.add_argument("--ssh-host")
    for command in (probe, send):
        command.add_argument("--protocol", default="https", choices=("https", "ssh"))
    for command in (send, resume):
        command.add_argument("--confirm-target", required=True,
                             help="The owner/repo explicitly confirmed by the user.")
    send.add_argument("--mode", required=True, choices=("create", "existing"))
    send.add_argument("--visibility", default="private", choices=("private", "public"))
    send.add_argument("--branch", required=True)
    send.add_argument("--head", required=True)
    send.add_argument("--repo-id", type=int)
    send.add_argument("--remote-head", choices=("empty",), help=argparse.SUPPRESS)
    send.add_argument("--description")
    send.add_argument("--homepage")
    send.add_argument("--topic", action="append", default=[])
    resume.add_argument("--repo-id", type=int)
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 4 and argv[0] == "_credential":
        try:
            credential(*argv[1:])
            return 0
        except Stop:
            return 1

    args = parser.parse_args(argv)
    report = {}
    try:
        if args.command == "accounts":
            report = accounts()
        elif args.command == "owners":
            matching(args.account, LOGIN, "account")
            gh = Github(args.account)
            report["personal"] = args.account
            try:
                pages = gh.api("user/orgs?per_page=100", paginate=True)
                report["organizations"] = [org["login"] for page in pages for org in page]
            except APIError as error:
                report.update(organizations=[], organization_listing_error=str(error))
        else:
            args.owner, args.repo = resolve_target(args.target, args.owner, args.repo, args.ssh_host)
            root = project_root(args.root)
            target = f"{args.owner}/{args.repo}"
            report.update(url=f"https://{HOST}/{target}", stage="preflight")
            if args.command == "inspect":
                matching(args.account, LOGIN, "account")
                report.update(account=args.account, protocol=args.protocol)
                inspect(args, root, Github(args.account), f"repos/{target}", target, report)
            else:
                if args.confirm_target.casefold() != target.casefold():
                    raise Stop("The confirmed owner/repo does not match the publication target.")
                with locked_journal(root, target) as journal:
                    if args.command == "resume":
                        if not journal.exists():
                            raise Stop("No recovery record exists for this project and destination.")
                        state = load_journal(journal, root, target)
                        run_publication(state, journal, report, args.repo_id)
                    else:
                        if journal.exists():
                            raise Stop("This destination already has a recovery record. Use resume to verify or continue.")
                        matching(args.account, LOGIN, "account")
                        plan = publication_plan(args, root)
                        local_commit(args)
                        state = {"version": 1, "plan": plan, "repository_id": args.repo_id,
                                 "operations": {"repository": "pending", "push": "pending", "metadata": "pending"}}
                        run_publication(state, journal, report)
    except (Stop, ValueError, OSError) as error:
        report["error"] = str(error)
        print(json.dumps(report, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
