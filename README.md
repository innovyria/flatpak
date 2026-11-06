# Innovyria Flatpak repository

Signed Flatpak repository for Innovyria's open-source apps, served from GitHub Pages at
**https://innovyria.github.io/flatpak/**. Apps use the GNOME runtime from Flathub and update
through `flatpak update` and GNOME Software.

## Install

| App | Install |
| --- | --- |
| [Markdown Editor](https://github.com/24icewolf42/markdown-editor) | [`.flatpakref`](https://innovyria.github.io/flatpak/io.github._24icewolf42.markdown-editor.flatpakref) |

```sh
flatpak install --user https://innovyria.github.io/flatpak/io.github._24icewolf42.markdown-editor.flatpakref
```

Or add the whole repository:

```sh
flatpak remote-add --user --if-not-exists innovyria https://innovyria.github.io/flatpak/innovyria.flatpakrepo
```

## How it works

- Each app builds its Flatpak bundle in its own CI and attaches it to a GitHub release, together
  with `SHA256SUMS`.
- [`publish.yml`](.github/workflows/publish.yml) runs every hour (and on demand). For each app in
  [`apps.json`](apps.json) it takes the latest release's `x86_64` bundle, checks it against the
  release checksums, imports it into the OSTree repository, and signs the commit.
- [`publish.py`](publish.py) then regenerates the signed summary, the AppStream data and static
  deltas (keeping the last two versions), and writes the install files.
- The result is deployed to the `gh-pages` branch as a single commit.

Commits and the summary are signed with the key `F6D1A2A3E1E0149DF213611D68D7D41936EF3AF6`
([`innovyria.asc`](innovyria.asc)). The private key exists only as the organization secret
`FLATPAK_GPG_PRIVATE_KEY`; its id is `FLATPAK_GPG_KEY_ID`.

To add an app: append it to `apps.json`. Its releases must carry a `*-x86_64.flatpak` bundle on
branch `stable` and a `SHA256SUMS` file.
