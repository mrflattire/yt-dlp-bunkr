# yt-dlp-bunkr

A yt-dlp plugin adding native support for bunkr.* file (`/f/`, `/v/`, `/i/`) and album (`/a/`) pages.

> **Not yet published to PyPI. Install directly from source using one of the methods below.****

## Installing

`curl_cffi` is a hard dependency of this plugin (not the usual yt-dlp's optional
`--impersonate` extra. Refer to "Why this exists" below), so however you install it,
make sure `curl_cffi` is present in the same environment yt-dlp runs from.

yt-dlp looks for a `yt_dlp_plugins` namespace folder in several standard locations
and loads plugins from *all* of them, as a no1 priority before it's inbuilt extractors. Pick whichever fits your setup:

### 1. Configuration directories (recommended for most installs)

Grab this repo's `yt_dlp_plugins/` folder and drop it into one of these you create on your machine:

**User plugins**
- `${XDG_CONFIG_HOME}/yt-dlp/plugins/yt-dlp-bunkr/yt_dlp_plugins/` (recommended on Linux/macOS)
- `${XDG_CONFIG_HOME}/yt-dlp-plugins/yt-dlp-bunkr/yt_dlp_plugins/`
- `${APPDATA}/yt-dlp/plugins/yt-dlp-bunkr/yt_dlp_plugins/` (recommended on Windows)
- `${APPDATA}/yt-dlp-plugins/yt-dlp-bunkr/yt_dlp_plugins/`
- `~/.yt-dlp/plugins/yt-dlp-bunkr/yt_dlp_plugins/`
- `~/yt-dlp-plugins/yt-dlp-bunkr/yt_dlp_plugins/`

**System plugins**
- `/etc/yt-dlp/plugins/yt-dlp-bunkr/yt_dlp_plugins/`
- `/etc/yt-dlp-plugins/yt-dlp-bunkr/yt_dlp_plugins/`

Then separately make sure `curl_cffi` is installed in that environment:
```bash
pip install curl_cffi
```

### 2. Next to the yt-dlp executable (recommended for portable installs)

Create a `yt-dlp-plugins` directory alongside the binary/source root and in it add the contents as below:
- Binary install: `<root-dir>/yt-dlp.exe`, `<root-dir>/yt-dlp-plugins/yt-dlp-bunkr/yt_dlp_plugins/`
- Source install: `<root-dir>/yt_dlp/__main__.py`, `<root-dir>/yt-dlp-plugins/yt-dlp-bunkr/yt_dlp_plugins/`

### 3. pip install (from source, until this is published)

```bash
pip install git+https://github.com/YOUR_USERNAME/yt-dlp-bunkr
# or, from a local checkout:
pip install /path/to/yt-dlp-bunkr
```

`curl_cffi` is declared in `pyproject.toml`, so this pulls it in automatically. Any
path on `PYTHONPATH` is also searched for a `yt_dlp_plugins` folder, so a plain
`pip install -e .` from this repo works too. Note that this doesn't apply to PyInstaller
builds.

### `.zip` / `.whl` archives

A `.zip`, `.egg`, or `.whl` with a `yt_dlp_plugins` namespace folder at its root is
also accepted directly in any of the config-directory locations above, e.g.
`${XDG_CONFIG_HOME}/yt-dlp/plugins/yt-dlp-bunkr.zip` containing
`yt_dlp_plugins/extractor/bunkr.py`. `python3 -m build --wheel` in this repo produces
one.

### Verifying it loaded

```bash
yt-dlp --verbose 2>&1 | grep -i plugin
```
Should show `Extractor Plugins: BunkrAlbumIE, BunkrIE` and the plugin directory it
found them in. If it's missing, double-check `curl_cffi` is actually importable in
the same Python environment yt-dlp itself is running from. A broken plugin import
is sometimes silently skipped rather than raising, so mismatched environments are
the most common cause of "it's just not there."

## Usage

Once installed, this works exactly like any other yt-dlp-supported site. Extractor
plugins do not need to be enabled or configured from the CLI. yt-dlp automatically
invokes a plugin whenever the input URL matches it, and plugins take priority over
any built-in extractor for the same URL.

```bash
yt-dlp https://bunkr.cr/f/some-file-slug
yt-dlp https://bunkr.cr/a/some-album-slug              # downloads every file in the album
yt-dlp --playlist-items 1-5 https://bunkr.cr/a/some-album-slug
```

Run with `--verbose` and confirm the log shows `[bunkr]` / `[bunkr:album]` and not
`[generic]` to verify the plugin actually loaded and is handling the URL.

## Why this exists

Mainline yt-dlp has no native Bunkr support (its generic extractor can't resolve
Bunkr's stream URLs), and Bunkr's token-signing endpoints sit behind what appears to
be TLS-fingerprint-based bot detection, not just header spoofing. This plugin talks
to Bunkr with `curl_cffi`'s browser impersonation directly, as its own explicit
dependency, rather than relying on yt-dlp's optional `--impersonate` extra (which is
frequently not bundled; Homebrew/Nix/Arch builds commonly ship without it).

There are two genuinely different signing flows, both confirmed against real
captured traffic, not guessed. 

- **Album-sourced** (`BunkrAlbumIE` dispatching into `BunkrIE`): a two-step mint
  metadata API, then sign, using the file's numeric id, passed through cheaply via
  a `#_fid=<id>` URL fragment so nothing is re-fetched.
- **Direct file-page visit**: a single page fetch for the embedded `jsCDN` value,
  then one sign call, no metadata API, no numeric id needed at all.

Albums are extracted lazily: visiting an album parses its file list and yields
references back to `BunkrIE` rather than minting everything up front, so
`--playlist-items`, `--max-downloads`, and download-archives all work normally, and
files outside your selection are never minted.

A shared, persistent `curl_cffi` session is used across requests (rather than a
fresh TLS handshake per call) with automatic reset-and-retry on failure. Repeated
cold handshakes are exactly the kind of pattern that trips fingerprint-based
rate-limiting on a site already doing TLS-level bot detection.

## Before you rely on this in CI

The `_TESTS` blocks use real, confirmed-working URLs, but Bunkr content can get
taken down. If you are to run a test and it starts failing, check whether the URLs in the tests block are still live before
assuming the extractor broke.

## 🛡️ Legal Notice

**yt-dlp-bunkr** is an independent project and is not affiliated with, authorized, maintained, or endorsed by yt-dlp or Bunkr. This tool is provided for educational and personal archival purposes only. Users are responsible for complying with the Terms of Service of the platforms they interact with and the copyrights of the content creators. Let that sink in; this project is for educational and research purposes only. The developers are not responsible for how this tool is utilized.