#!/usr/bin/env python

import getpass
import json
import pathlib
import subprocess
import sys
import time


def github_commits():
    OAUTH_TOKEN = getpass.getpass("OAuth Token? ")
    COMMIT_API = (
        f'curl -H "Authorization: token {OAUTH_TOKEN}" '
        f"https://api.github.com/repos/python-websockets/websockets/git/commits/:sha"
    )

    commits = []

    head = subprocess.check_output(
        "git rev-parse origin/main",
        shell=True,
        text=True,
    ).strip()
    todo = [head]
    seen = set()

    while todo:
        sha = todo.pop(0)
        commit = subprocess.check_output(COMMIT_API.replace(":sha", sha), shell=True)
        commits.append(commit)
        seen.add(sha)
        for parent in json.loads(commit)["parents"]:
            sha = parent["sha"]
            if sha not in seen and sha not in todo:
                todo.append(sha)
        time.sleep(1)  # rate throttling

    return commits


def main(corpus):
    data = github_commits()
    for num, content in enumerate(reversed(data)):
        (corpus / f"{num:04d}.json").write_bytes(content)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [directory]")
        sys.exit(2)
    main(pathlib.Path(sys.argv[1]))
