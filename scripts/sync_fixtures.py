#!/usr/bin/env python3
"""Regenerate fixtures.json from the public Chauvet-Pro firmware repos.

For each public repo with a firmware/ directory, point firmware_url at the
newest .zip in that directory, pinned to the latest release tag when the repo
has releases (otherwise the default branch).

Hand-edited unrival_id / aliases are preserved. Writes only when something
changed, and bumps the top-level version when it does.

Env: GITHUB_TOKEN (optional locally, provided by Actions).
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ORG = "Chauvet-Pro"
API = "https://api.github.com"
OUT = os.path.join(os.path.dirname(__file__), os.pardir, "fixtures.json")
PROPS = os.path.join(os.path.dirname(__file__), os.pardir, "productsProperties.json")


def api(path):
    req = urllib.request.Request(API + path, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def public_repos():
    page, out = 1, []
    while True:
        batch = api(f"/orgs/{ORG}/repos?type=public&per_page=100&page={page}")
        if not batch:
            return out
        out += batch
        page += 1


FAMILIES = ["COLORado", "COLORdash", "Maverick", "Ovation", "Rogue", "STRIKE", "WELL",
            "EPIX", "onAir", "Nexus", "Legend", "MVP", "NET-X", "PVP", "Synapse"]


def norm(s):
    return "".join(c for c in s.upper() if c.isalnum())


def family_of(*names):
    for f in sorted(FAMILIES, key=len, reverse=True):
        if any(norm(n).startswith(norm(f)) for n in names):
            return f
    return None


def pick_latest(names):
    """Newest firmware zip. Names sort chronologically for V1.YYMMDD and V<n>_<date>."""
    zips = sorted(n for n in names if n.lower().endswith(".zip"))
    return zips[-1] if zips else None


def merge(old, new):
    """Keep hand-maintained fields from the existing entry."""
    if not old:
        return new
    return {**new, "unrival_id": old.get("unrival_id") or new["unrival_id"],
            "family": old.get("family") or new["family"],
            "aliases": sorted(set(old.get("aliases", [])) | set(new["aliases"]))}


def build():
    ids = {norm(p["name"]): p["deviceModelId"]
           for p in json.load(open(PROPS))["products"]}
    fixtures = {}
    for r in sorted(public_repos(), key=lambda r: r["name"]):
        name = r["name"]
        release = api(f"/repos/{ORG}/{name}/releases/latest")
        ref = release["tag_name"] if release else r["default_branch"]
        listing = api(f"/repos/{ORG}/{name}/contents/firmware?ref={urllib.parse.quote(ref)}")
        if not isinstance(listing, list):
            continue
        latest = pick_latest(f["name"] for f in listing)
        if not latest:
            continue
        label = (r["description"] or name).strip()
        fixtures[label] = {
            "unrival_id": ids.get(norm(label)) or ids.get(norm(name)),
            "family": family_of(label, name),
            "aliases": [name],
            "firmware_version": release["tag_name"] if release else None,
            "released_at": release["published_at"] if release else None,
            "release_notes": (release.get("body") or "").strip() or None if release else None,
            "firmware_url": f"https://github.com/{ORG}/{name}/raw/"
                            f"{urllib.parse.quote(ref)}/firmware/{urllib.parse.quote(latest)}",
        }
    return fixtures


def selftest():
    assert pick_latest(["V1.250813.zip", "V1.260609.zip", "README.md"]) == "V1.260609.zip"
    assert pick_latest(["README.md"]) is None
    assert family_of("COLORdash Par H7X IP", "COLORDASHPARH7XIP") == "COLORdash"
    assert family_of("COLORado Solo Bar 1", "COLORADOSOLOBAR1") == "COLORado"
    assert family_of("onAir Panel 1 IP", "ONAIRPANEL1IP") == "onAir"
    assert family_of("F4X1", "F4X1") is None
    kept = merge({"unrival_id": 2629, "family": None, "aliases": ["MS1F"]},
                 {"unrival_id": None, "family": "Maverick", "aliases": ["MAVERICKSTORM1FLEX"]})
    assert kept == {"unrival_id": 2629, "family": "Maverick",
                    "aliases": ["MAVERICKSTORM1FLEX", "MS1F"]}
    assert merge(None, {"unrival_id": 1})["unrival_id"] == 1
    print("selftest ok")


def main():
    if "--selftest" in sys.argv:
        return selftest()

    old = json.load(open(OUT)) if os.path.exists(OUT) else {"version": 0, "fixtures": {}}
    fixtures = {k: merge(old["fixtures"].get(k), v) for k, v in build().items()}
    if fixtures == old["fixtures"]:
        print(f"no change ({len(fixtures)} fixtures)")
        return
    with open(OUT, "w") as f:
        json.dump({"version": old["version"] + 1, "fixtures": fixtures}, f, indent=2)
        f.write("\n")
    print(f"updated: {len(fixtures)} fixtures, version {old['version'] + 1}")


if __name__ == "__main__":
    main()
