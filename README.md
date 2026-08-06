# yt-dlp-bunkr

A yt-dlp plugin adding native support for bunkr.* file (`/f/`, `/v/`, `/i/`) and album (`/a/`) pages.

**NOT USABLE YET. Still in Development. fork to help.**

## Install

Requires yt-dlp>=2024.03.10

```bash
pip install yt-dlp

pip install git+https://github.com/mrflattire/yt-dlp-bunkr.git
```

## Usage

Works exactly like any other yt-dlp-supported site — no flags needed:

```bash
yt-dlp https://bunkr.cr/f/some-file-slug
yt-dlp https://bunkr.cr/a/some-album-slug              # downloads every file in the album
yt-dlp --playlist-items 1-5 https://bunkr.cr/a/some-album-slug
```

## Why this exists

Bunkr's stream URLs need a two-step, TLS-fingerprint-sensitive token mint
(see `yt_dlp_plugins/extractor/bunkr.py`'s module docstring) that mainline
yt-dlp's generic extractor can't resolve. This plugin talks to the mint API
directly using `curl_cffi` (a hard dependency of this package, not
yt-dlp's optional `--impersonate` extra, which is frequently not bundled
in common installs).

Album pages are extracted lazily: visiting an album parses the file list
and yields references back to the single-file extractor, so
`--playlist-items`, `--max-downloads`, and download-archives all work
normally, and files outside your selection are never minted at all.

## 🛡️ Legal Notice

**ytdlp-bunkr** is an independent project and is not affiliated with, authorized, maintained, or endorsed by Bunkr. This tool is provided for educational and personal archival purposes only. Users are responsible for complying with the Terms of Service of the platforms they interact with and the copyrights of the content creators. This project is for educational and research purposes only. The developers are not responsible for how this tool is utilized.
