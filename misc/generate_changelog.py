"""Generate the changelog for a mypy release."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass


def find_all_release_branches() -> list[tuple[int, int]]:
    result = subprocess.run(["git", "branch", "-r"], text=True, capture_output=True, check=True)
    versions = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if m := re.match(r"origin/release-([0-9]+)\.([0-9]+)$", line):
            major = int(m.group(1))
            minor = int(m.group(2))
            versions.append((major, minor))
    return versions


def git_merge_base(rev1: str, rev2: str) -> str:
    result = subprocess.run(
        ["git", "merge-base", rev1, rev2], text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


@dataclass
class CommitInfo:
    commit: str
    author: str
    title: str
    pr_number: int | None


def normalize_author(author: str) -> str:
    # Some ad-hoc rules to get more consistent author names.
    if author == "AlexWaygood":
        return "Alex Waygood"
    elif author == "jhance":
        return "Jared Hance"
    return author


def git_commit_log(rev1: str, rev2: str) -> list[CommitInfo]:
    result = subprocess.run(
        ["git", "log", "--pretty=%H\t%an\t%s", f"{rev1}..{rev2}"],
        text=True,
        capture_output=True,
        check=True,
    )
    commits = []
    for line in result.stdout.splitlines():
        commit, author, title = line.strip().split("\t", 2)
        pr_number = None
        if m := re.match(r".*\(#([0-9]+)\) *$", title):
            pr_number = int(m.group(1))
            title = re.sub(r" *\(#[0-9]+\) *$", "", title)

        author = normalize_author(author)
        entry = CommitInfo(commit, author, title, pr_number)
        commits.append(entry)
    return commits


def filter_omitted_commits(commits: list[CommitInfo]) -> list[CommitInfo]:
    result = []
    for c in commits:
        title = c.title
        keep = True
        if title.startswith("Sync typeshed"):
            # Typeshed syncs aren't mentioned in release notes
            keep = False
        if title.startswith(
            (
                "Revert sum literal integer change",
                "Remove use of LiteralString in builtins",
                "Revert typeshed ctypes change",
                "Revert use of `ParamSpec` for `functools.wraps`",
            )
        ):
            # These are generated by a typeshed sync.
            keep = False
        if re.search(r"(bump|update).*version.*\+dev", title.lower()):
            # Version number updates aren't mentioned
            keep = False
        if "pre-commit autoupdate" in title:
            keep = False
        if title.startswith(("Update commit hashes", "Update hashes")):
            # Internal tool change
            keep = False
        if keep:
            result.append(c)
    return result


def normalize_title(title: str) -> str:
    # We sometimes add a title prefix when cherry-picking commits to a
    # release branch. Attempt to remove these prefixes so that we can
    # match them to the corresponding main branch.
    if m := re.match(r"\[release [0-9.]+\] *", title, flags=re.I):
        title = title.replace(m.group(0), "")
    return title


def filter_out_commits_from_old_release_branch(
    new_commits: list[CommitInfo], old_commits: list[CommitInfo]
) -> list[CommitInfo]:
    old_titles = {normalize_title(commit.title) for commit in old_commits}
    result = []
    for commit in new_commits:
        drop = False
        if normalize_title(commit.title) in old_titles:
            drop = True
        if normalize_title(f"{commit.title} (#{commit.pr_number})") in old_titles:
            drop = True
        if not drop:
            result.append(commit)
        else:
            print(f'NOTE: Drop "{commit.title}", since it was in previous release branch')
    return result


def find_changes_between_releases(old_branch: str, new_branch: str) -> list[CommitInfo]:
    merge_base = git_merge_base(old_branch, new_branch)
    print(f"Merge base: {merge_base}")
    new_commits = git_commit_log(merge_base, new_branch)
    old_commits = git_commit_log(merge_base, old_branch)

    # Filter out some commits that won't be mentioned in release notes.
    new_commits = filter_omitted_commits(new_commits)

    # Filter out commits cherry-picked to old branch.
    new_commits = filter_out_commits_from_old_release_branch(new_commits, old_commits)

    return new_commits


def format_changelog_entry(c: CommitInfo) -> str:
    """
    s = f" * {c.commit[:9]} - {c.title}"
    if c.pr_number:
        s += f" (#{c.pr_number})"
    s += f" ({c.author})"
    """
    s = f" * {c.title} ({c.author}"
    if c.pr_number:
        s += f", PR [{c.pr_number}](https://github.com/python/mypy/pull/{c.pr_number})"
    s += ")"

    return s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", help="target mypy version (form X.Y)")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    version: str = args.version
    local: bool = args.local

    if not re.match(r"[0-9]+\.[0-9]+$", version):
        sys.exit(f"error: Release must be of form X.Y (not {version!r})")
    major, minor = (int(component) for component in version.split("."))

    if not local:
        print("Running 'git fetch' to fetch all release branches...")
        subprocess.run(["git", "fetch"], check=True)

    if minor > 0:
        prev_major = major
        prev_minor = minor - 1
    else:
        # For a x.0 release, the previous release is the most recent (x-1).y release.
        all_releases = sorted(find_all_release_branches())
        if (major, minor) not in all_releases:
            sys.exit(f"error: Can't find release branch for {major}.{minor} at origin")
        for i in reversed(range(len(all_releases))):
            if all_releases[i][0] == major - 1:
                prev_major, prev_minor = all_releases[i]
                break
        else:
            sys.exit("error: Could not determine previous release")
    print(f"Generating changelog for {major}.{minor}")
    print(f"Previous release was     {prev_major}.{prev_minor}")

    new_branch = f"origin/release-{major}.{minor}"
    old_branch = f"origin/release-{prev_major}.{prev_minor}"

    changes = find_changes_between_releases(old_branch, new_branch)

    print()
    for c in changes:
        print(format_changelog_entry(c))


if __name__ == "__main__":
    main()
