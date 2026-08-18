#!/usr/bin/env python3
"""Put firmware-repo-release-hook.yml on every firmware repo that lacks it.

sync_fixtures.py adds new public firmware repos to fixtures.json, so running
this straight after the sync enrolls them with no one touching a repo.

Env: GITHUB_TOKEN — needs Contents: read-write on the org (the same
UNRIVAL_DISPATCH_TOKEN the hook itself uses).
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

from sync_fixtures import API, ORG, api, public_repos

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "firmware-repo-release-hook.yml")
FIXTURES = os.path.join(HERE, os.pardir, "fixtures.json")
PATH = ".github/workflows/notify-unrival.yml"


def pick_repos(fixtures, public):
    """Aliases that are real repo names — an alias may be a hand-added nickname."""
    return sorted({a for v in fixtures.values() for a in v["aliases"]} & public)


def put(path, payload):
    req = urllib.request.Request(
        API + path, method="PUT", data=json.dumps(payload).encode(),
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]})
    urllib.request.urlopen(req, timeout=30).close()


def selftest():
    fx = {"X": {"aliases": ["MS1F", "ZED"]}, "Y": {"aliases": ["GONE"]}}
    assert pick_repos(fx, {"ZED", "OTHER"}) == ["ZED"]
    assert pick_repos(fx, {"OTHER"}) == []
    assert open(HOOK).read().startswith("# Managed by Chauvet-Pro/UNRIVAL")
    print("selftest ok")


def main():
    if "--selftest" in sys.argv:
        return selftest()

    body = open(HOOK, "rb").read()
    repos = pick_repos(json.load(open(FIXTURES))["fixtures"],
                       {r["name"] for r in public_repos()})
    added = failed = 0
    for name in repos:
        if api(f"/repos/{ORG}/{name}/contents/{PATH}"):
            continue
        try:
            put(f"/repos/{ORG}/{name}/contents/{PATH}",
                {"message": "Notify UNRIVAL on release publish",
                 "content": base64.b64encode(body).decode()})
            added += 1
            print("hooked " + name)
        except urllib.error.HTTPError as e:
            failed += 1
            print(f"FAIL {name}: {e.code} {e.read()[:120]}", file=sys.stderr)
    print(f"{len(repos)} repos checked, {added} newly hooked, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
