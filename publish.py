#!/usr/bin/env python3
"""Update the Innovyria Flatpak repository in SITE (the GitHub Pages tree).

    publish.py SITE [--force]

For every app in apps.json, the latest GitHub release's x86_64 Flatpak bundle
is checked against the release's SHA256SUMS and imported into the OSTree
repository SITE/repo, signed with the repository key. The summary, AppStream
data and static deltas are then regenerated and the install files
(.flatpakrepo, .flatpakref, index.html) rewritten.

Environment: FLATPAK_GPG_PRIVATE_KEY (armored secret key), FLATPAK_GPG_KEY_ID,
GH_TOKEN (optional, raises the API rate limit). Writes `changed=true|false`
to $GITHUB_OUTPUT when set.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_URL = "https://innovyria.github.io/flatpak"
REPO_URL = f"{BASE_URL}/repo/"
FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"
TITLE = "Innovyria"
COMMENT = "Open-source apps from Innovyria"
BRANCH = "stable"
ARCH = "x86_64"


def api(path: str) -> dict:
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={"Accept": "application/vnd.github+json"})
    if os.environ.get("GH_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GH_TOKEN']}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as r, dest.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def run(*cmd: str) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> int:
    site = Path(sys.argv[1]).resolve()
    force = "--force" in sys.argv[2:]
    repo = site / "repo"
    state = site / "state"
    apps = json.loads((HERE / "apps.json").read_text(encoding="utf-8"))
    key_id = os.environ["FLATPAK_GPG_KEY_ID"].strip()

    gpg_home = Path(tempfile.mkdtemp(prefix="gpg-"))
    gpg_home.chmod(0o700)
    subprocess.run(["gpg", "--homedir", str(gpg_home), "--batch", "--import"],
                   input=os.environ["FLATPAK_GPG_PRIVATE_KEY"].encode(), check=True)
    sign = [f"--gpg-sign={key_id}", f"--gpg-homedir={gpg_home}"]

    if not (repo / "config").exists():
        run("ostree", "init", "--mode=archive-z2", f"--repo={repo}")
        changed = True
    else:
        changed = force
    state.mkdir(parents=True, exist_ok=True)

    for app in apps:
        release = api(f"repos/{app['source']}/releases/latest")
        tag = release["tag_name"]
        marker = state / app["id"]
        if marker.exists() and marker.read_text().strip() == tag:
            print(f"{app['id']}: {tag} already published")
            continue
        assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
        bundle_name = next((n for n in assets if n.endswith(f"-{ARCH}.flatpak")), None)
        if bundle_name is None or "SHA256SUMS" not in assets:
            print(f"{app['id']}: release {tag} has no {ARCH} bundle with checksums; skipped")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / bundle_name
            sums = Path(tmp) / "SHA256SUMS"
            download(assets[bundle_name], bundle)
            download(assets["SHA256SUMS"], sums)
            expected = next((line.split()[0] for line in sums.read_text().splitlines() if line.endswith(f"  {bundle_name}")), None)
            actual = hashlib.sha256(bundle.read_bytes()).hexdigest()
            if expected != actual:
                raise SystemExit(f"{bundle_name}: checksum mismatch ({actual} != {expected})")
            run("flatpak", "build-import-bundle", *sign, str(repo), str(bundle))
        marker.write_text(tag + "\n")
        print(f"{app['id']}: imported {tag}")
        changed = True

    if changed:
        run("flatpak", "build-update-repo", *sign, "--generate-static-deltas", "--prune", "--prune-depth=2",
            f"--title={TITLE}", f"--comment={COMMENT}", f"--homepage={BASE_URL}/", f"--default-branch={BRANCH}",
            str(repo))
        write_install_files(site, apps, gpg_home, key_id)

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(f"changed={'true' if changed else 'false'}\n")
    return 0


def write_install_files(site: Path, apps: list[dict], gpg_home: Path, key_id: str) -> None:
    public = subprocess.run(["gpg", "--homedir", str(gpg_home), "--export", key_id], capture_output=True, check=True).stdout
    armored = subprocess.run(["gpg", "--homedir", str(gpg_home), "--armor", "--export", key_id],
                             capture_output=True, check=True).stdout
    key_b64 = base64.b64encode(public).decode()
    (site / "innovyria.gpg").write_bytes(public)
    (site / "innovyria.asc").write_bytes(armored)
    (site / ".nojekyll").write_text("")
    (site / "innovyria.flatpakrepo").write_text(
        "[Flatpak Repo]\n"
        f"Title={TITLE}\n"
        f"Url={REPO_URL}\n"
        f"Homepage={BASE_URL}/\n"
        f"Comment={COMMENT}\n"
        "Description=Open-source software crafted by an autonomous software development lifecycle.\n"
        f"DefaultBranch={BRANCH}\n"
        f"GPGKey={key_b64}\n"
    )
    rows = []
    for app in apps:
        (site / f"{app['id']}.flatpakref").write_text(
            "[Flatpak Ref]\n"
            f"Name={app['id']}\n"
            f"Branch={BRANCH}\n"
            f"Title={app['name']}\n"
            f"Url={REPO_URL}\n"
            "SuggestRemoteName=innovyria\n"
            f"RuntimeRepo={FLATHUB}\n"
            "IsRuntime=false\n"
            f"Homepage=https://github.com/{app['source']}\n"
            f"GPGKey={key_b64}\n"
        )
        rows.append(
            f'<li><h2><a href="https://github.com/{html.escape(app["source"])}">{html.escape(app["name"])}</a></h2>'
            f"<p>{html.escape(app['summary'])}</p>"
            f'<p><a class="button" href="{html.escape(app["id"])}.flatpakref">Install</a></p>'
            f"<pre>flatpak install --user {BASE_URL}/{html.escape(app['id'])}.flatpakref</pre></li>"
        )
    fingerprint = key_id.upper()
    (site / "index.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Innovyria Flatpak repository</title>
<style>
  body {{ font: 16px/1.5 system-ui, sans-serif; max-width: 46rem; margin: 2rem auto; padding: 0 1rem; color: #241f31; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #1d1d20; color: #deddda; }} a {{ color: #99c1f1; }} }}
  ul {{ list-style: none; padding: 0; }}
  li {{ border: 1px solid #8884; border-radius: 12px; padding: 0 1rem; margin: 1rem 0; }}
  pre {{ background: #8882; padding: .6rem .8rem; border-radius: 8px; overflow-x: auto; }}
  .button {{ display: inline-block; padding: .4rem 1rem; border-radius: 8px; background: #3584e4; color: #fff; text-decoration: none; font-weight: 600; }}
  code {{ font-size: .9em; }}
</style>
</head>
<body>
<h1>Innovyria Flatpak repository</h1>
<p>Open-source apps from <a href="https://github.com/innovyria">Innovyria</a>, crafted by an autonomous software
development lifecycle. Apps run on the GNOME runtime from Flathub and update with <code>flatpak update</code> or
GNOME Software.</p>
<ul>
{chr(10).join(rows)}
</ul>
<h2>Add the whole repository</h2>
<pre>flatpak remote-add --user --if-not-exists innovyria {BASE_URL}/innovyria.flatpakrepo</pre>
<p>Commits and the repository summary are signed with the key <code>{fingerprint}</code>
(<a href="innovyria.asc">innovyria.asc</a>).</p>
</body>
</html>
""")


if __name__ == "__main__":
    raise SystemExit(main())
