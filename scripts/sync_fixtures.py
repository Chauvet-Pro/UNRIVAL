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
import re
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


def build_date(name):
    """The YYMMDD stamp in a firmware name, if it carries one."""
    stamps = re.findall(r"(?<!\d)(2\d(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))(?!\d)", name)
    return stamps[0] if stamps else None


def pick_latest(names, tag=None):
    """The zip a release ships, else the newest by name.

    Most repos name every zip `V1.YYMMDD.zip`, which sorts chronologically. Some
    mix in a second scheme (`V1.00.003-260724-2.zip`, `A4073F-...-V1.251014-...zip`)
    that sorts *below* the plain names, so sorting alone hands back a build years
    older than the release it is labelled with. When the tag carries a date stamp,
    prefer the zip stamped the same day; fall back to sorting when none does.
    """
    zips = sorted(n for n in names if n.lower().endswith(".zip"))
    if not zips:
        return None
    stamp = build_date(tag or "")
    if stamp:
        dated = [n for n in zips if build_date(n) == stamp]
        if dated:
            return dated[-1]
    return zips[-1]


def firmware_dir(listing):
    """Name of the firmware directory as the repo actually spells it.

    The contents API is case-sensitive, so asking for `firmware` 404s on the
    repos that use `Firmware` — they were being skipped entirely rather than
    reported. Match on the root listing instead and keep the real casing, which
    the download URL needs.
    """
    if not isinstance(listing, list):
        return None
    for entry in listing:
        if entry["type"] == "dir" and entry["name"].lower() == "firmware":
            return entry["name"]
    return None


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
        quoted_ref = urllib.parse.quote(ref)
        fw_dir = firmware_dir(api(f"/repos/{ORG}/{name}/contents?ref={quoted_ref}"))
        if not fw_dir:
            continue
        listing = api(f"/repos/{ORG}/{name}/contents/{fw_dir}?ref={quoted_ref}")
        if not isinstance(listing, list):
            continue
        latest = pick_latest((f["name"] for f in listing), ref if release else None)
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
                            f"{quoted_ref}/{fw_dir}/{urllib.parse.quote(latest)}",
        }
    return fixtures


def selftest():
    assert pick_latest(["V1.250813.zip", "V1.260609.zip", "README.md"]) == "V1.260609.zip"
    assert pick_latest(["README.md"]) is None
    # A release whose zip uses the other naming scheme sorts below the plain names.
    mixed = ["V1.00.003-260724-2.zip", "V1.260210.zip", "V1.260319.zip"]
    assert pick_latest(mixed, "V1.260724") == "V1.00.003-260724-2.zip"
    assert pick_latest(mixed) == "V1.260319.zip"          # no tag -> unchanged
    assert pick_latest(mixed, "V1.231011") == "V1.260319.zip"  # tag matches nothing -> unchanged
    assert build_date("A4073F-COLORADO PXL BAR 16-V1.251014-251027-1.zip") == "251014"
    assert build_date("V1.1.6.zip") is None
    assert family_of("COLORdash Par H7X IP", "COLORDASHPARH7XIP") == "COLORdash"
    assert family_of("COLORado Solo Bar 1", "COLORADOSOLOBAR1") == "COLORado"
    assert family_of("onAir Panel 1 IP", "ONAIRPANEL1IP") == "onAir"
    assert family_of("F4X1", "F4X1") is None
    assert firmware_dir([{"type": "dir", "name": "Firmware"}]) == "Firmware"
    assert firmware_dir([{"type": "dir", "name": "firmware"}]) == "firmware"
    assert firmware_dir([{"type": "file", "name": "firmware"}]) is None
    assert firmware_dir([{"type": "dir", "name": "docs"}]) is None
    assert firmware_dir(None) is None
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
