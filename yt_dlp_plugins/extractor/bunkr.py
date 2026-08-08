import contextlib
import re
import time
import urllib.parse

from curl_cffi import requests as curl_requests
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError, determine_ext, int_or_none

_BASE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Origin': 'https://bunkr.cr',
    'Referer': 'https://bunkr.cr/',
}

_ALBUM_FILES_RE = re.compile(r'(?:window\.)?albumFiles\s*=\s*\[(.*?)\];?', re.DOTALL)
_ALBUM_OBJECT_RE = re.compile(r'\{([^}]+)\}', re.DOTALL)
_ALBUM_FIELD_RE = re.compile(r'(\w+):\s*(?:"([^"]*)"|(\d+))')

_JS_CDN_RE = re.compile(r'var\s+jsCDN\s*=\s*"([^"]*)"')
_JS_TYPE_RE = re.compile(r'var\s+jsType\s*=\s*"([^"]*)"')
_OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')
_TITLE_TAG_RE = re.compile(r'<title>(.*?)</title>', re.DOTALL)

_SHARED_SESSION = None


def _get_session():
    """Returns a persistent curl_cffi Session to keep TCP/TLS sockets open."""
    global _SHARED_SESSION
    if _SHARED_SESSION is None:
        _SHARED_SESSION = curl_requests.Session(impersonate='chrome124')
    return _SHARED_SESSION


def _reset_session():
    """Resets the persistent session if Cloudflare drops the TCP socket."""
    global _SHARED_SESSION
    if _SHARED_SESSION is not None:
        with contextlib.suppress(Exception):
            _SHARED_SESSION.close()
        _SHARED_SESSION = None


def _strip_bunkr_suffix(raw_title):
    return re.sub(r'\s*[\|\-]\s*Bunkr\s*$', '', raw_title.strip(), flags=re.IGNORECASE)


def _unescape_js_string(s):
    return s.replace('\\/', '/')


def _fetch_page_html(url):
    """Fetches HTML using the shared session with automated reset retries."""
    last_exception = None
    for attempt in range(3):
        try:
            session = _get_session()
            res = session.get(url, headers=_BASE_HEADERS, timeout=30)
            res.raise_for_status()
            return res.text
        except Exception as e:
            last_exception = e
            _reset_session()
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))

    raise ExtractorError(f'Failed to fetch page HTML after retries: {last_exception}', expected=True)


def _parse_album_files(html):
    match = _ALBUM_FILES_RE.search(html)
    if not match:
        return []

    files = []
    for obj_str in _ALBUM_OBJECT_RE.findall(match.group(1)):
        meta = {}
        for key, str_val, num_val in _ALBUM_FIELD_RE.findall(obj_str):
            meta[key] = int(num_val) if num_val else str_val
        if not meta:
            continue

        slug = meta.get('slug') or meta.get('name')
        if not slug:
            continue

        files.append(
            {
                'true_file_id': meta.get('id'),
                'slug': slug,
                'title': meta.get('original') or meta.get('name', slug),
                'size': meta.get('size'),
            },
        )
    return files


def _mint_via_album_flow(true_file_id):
    """Album-sourced flow using a persistent HTTP/2 session to prevent TLS handshake spam."""
    if not true_file_id or true_file_id == 'None':
        raise ExtractorError(f'Invalid or empty Bunkr file id: {true_file_id!r}', expected=True)

    mint_headers = {
        **_BASE_HEADERS,
        'Content-Type': 'application/json',
        'Origin': 'https://dl.bunkr.cr',
        'Referer': f'https://dl.bunkr.cr/file/{true_file_id}',
    }

    last_exception = None
    for attempt in range(3):
        try:
            session = _get_session()

            # Step 1: Query Metadata API
            meta_res = session.post(
                'https://dl.bunkr.cr/api/_001_v2',
                json={'id': str(true_file_id)},
                headers=mint_headers,
                timeout=30,
            )
            meta_res.raise_for_status()
            meta_data = meta_res.json()

            cdn_host = meta_data.get('mediafiles')
            storage_path = meta_data.get('path')
            original_name = meta_data.get('original')

            if not all([cdn_host, storage_path, original_name]):
                raise ExtractorError(
                    f'Bunkr mint API returned no usable data for id {true_file_id!r} '
                    '(album/file may have been taken down)',
                    expected=True,
                )

            # Step 2: Sign path
            encoded_path = urllib.parse.quote(storage_path)
            sign_res = session.get(
                f'https://glb-apisign.cdn.cr/sign?path={encoded_path}',
                headers=mint_headers,
                timeout=30,
            )
            sign_res.raise_for_status()
            sign_data = sign_res.json()

            token = sign_data.get('token')
            ex = sign_data.get('ex')
            if not token:
                raise ExtractorError(
                    f'Bunkr sign API returned no token for id {true_file_id!r}', expected=True,
                )

            encoded_name = urllib.parse.quote(original_name)
            direct_url = f'{cdn_host}{storage_path}?n={encoded_name}&token={token}&ex={ex}'
            return direct_url, original_name, None

        except ExtractorError:
            raise
        except Exception as e:
            last_exception = e
            _reset_session()
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))

    raise ExtractorError(f'Failed to mint file {true_file_id} after retries: {last_exception}')


def _mint_via_direct_page_flow(slug):
    """Standalone-visit flow using a persistent HTTP/2 session."""
    html = _fetch_page_html(f'https://bunkr.cr/f/{slug}')

    cdn_match = _JS_CDN_RE.search(html)
    if not cdn_match:
        raise ExtractorError(
            f'Could not find jsCDN on Bunkr file page {slug!r} '
            '(page structure may have changed since this extractor was written)',
            expected=True,
        )
    js_cdn = _unescape_js_string(cdn_match.group(1))

    type_match = _JS_TYPE_RE.search(html)
    js_type = _unescape_js_string(type_match.group(1)) if type_match else None

    og_match = _OG_TITLE_RE.search(html)
    if og_match:
        original_name = og_match.group(1)
    else:
        title_match = _TITLE_TAG_RE.search(html)
        original_name = _strip_bunkr_suffix(title_match.group(1)) if title_match else slug

    parsed = urllib.parse.urlparse(js_cdn)
    decoded_path = urllib.parse.unquote(parsed.path)

    last_exception = None
    for attempt in range(3):
        try:
            session = _get_session()
            sign_res = session.get(
                f"https://glb-apisign.cdn.cr/sign?path={urllib.parse.quote(decoded_path, safe='')}",
                headers=_BASE_HEADERS,
                timeout=30,
            )
            sign_res.raise_for_status()
            sign_data = sign_res.json()

            token = sign_data.get('token')
            ex = sign_data.get('ex')
            if not token:
                raise ExtractorError(f'Bunkr sign API returned no token for {slug!r}', expected=True)

            query = dict(urllib.parse.parse_qsl(parsed.query))
            query['token'] = token
            query['ex'] = ex
            direct_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))

            return direct_url, original_name, js_type

        except ExtractorError:
            raise
        except Exception as e:
            last_exception = e
            _reset_session()
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))

    raise ExtractorError(f'Failed to sign standalone URL for {slug} after retries: {last_exception}')


class BunkrIE(InfoExtractor):
    IE_NAME = 'bunkr'
    IE_DESC = 'bunkr.* single file'
    _VALID_URL = r'https?://(?:www\.)?bunkr\.\w+/(?:f|v|i)/(?P<id>[\w-]+)'

    _TESTS = [
        {
            'url': 'https://bunkr.cr/f/HkN6n4n9F7Wbl',
            'info_dict': {
                'id': 'HkN6n4n9F7Wbl',
                'ext': 'mp4',
                'title': 'Natalie Roush Onlyfans LEAK by SauceSenpai (217)',
            },
        },
    ]

    def _real_extract(self, url):
        slug = self._match_id(url)
        fragment = urllib.parse.urlparse(url).fragment
        fid_match = re.search(r'_fid=(\d+)', fragment) if fragment else None

        try:
            if fid_match:
                direct_url, original_name, js_type = _mint_via_album_flow(fid_match.group(1))
            else:
                direct_url, original_name, js_type = _mint_via_direct_page_flow(slug)
        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError(
                f'Failed to resolve a download URL for {slug}: {e}', expected=False,
            ) from e

        ext = determine_ext(original_name, default_ext=None)
        if not ext and js_type:
            ext = js_type.split('/')[-1]
        ext = ext or 'mp4'
        title = original_name.rsplit('.', 1)[0] if '.' in original_name else original_name

        return {
            'id': slug,
            'title': title,
            'url': direct_url,
            'ext': ext,
            'http_headers': _BASE_HEADERS,
        }


class BunkrAlbumIE(InfoExtractor):
    IE_NAME = 'bunkr:album'
    IE_DESC = 'bunkr.* album (playlist)'
    _VALID_URL = r'https?://(?:www\.)?bunkr\.\w+/a/(?P<id>[\w-]+)'

    _TESTS = [
        {
            'url': 'https://bunkr.cr/a/zz1fFSEM',
            'info_dict': {
                'id': 'zz1fFSEM',
                'title': 'Natalie Roush ALL OF VIDS FULL by',
            },
            'playlist_mincount': 1,
        },
    ]

    def _real_extract(self, url):
        album_slug = self._match_id(url)

        parsed_url = urllib.parse.urlparse(url)
        query = dict(urllib.parse.parse_qsl(parsed_url.query))
        if query.get('advanced') != '1':
            query['advanced'] = '1'
            url = urllib.parse.urlunparse(parsed_url._replace(query=urllib.parse.urlencode(query)))

        html = _fetch_page_html(url)

        title_match = _TITLE_TAG_RE.search(html)
        album_title = _strip_bunkr_suffix(title_match.group(1)) if title_match else None

        files = _parse_album_files(html)
        if not files:
            raise ExtractorError(
                f'No files found in Bunkr album {album_slug} '
                '(album may be empty, taken down, or the page structure changed)',
                expected=True,
            )

        def entries():
            for f in files:
                file_url = f"https://bunkr.cr/f/{f['slug']}"
                if f.get('true_file_id'):
                    file_url += f"#_fid={f['true_file_id']}"
                yield self.url_result(
                    file_url,
                    ie=BunkrIE,
                    video_id=f['slug'],
                    video_title=f['title'],
                    filesize=int_or_none(f.get('size')),
                )

        return self.playlist_result(entries(), album_slug, album_title)