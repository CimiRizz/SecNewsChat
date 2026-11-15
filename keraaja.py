"""Lue julkisten uutisjuttujen kommentointitila kustantajan sivudatasta."""
import json
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOSTS = {'IS': {'is.fi', 'www.is.fi'}, 'IL': {'iltalehti.fi', 'www.iltalehti.fi'}}
PATTERNS = {'IS': re.compile(r'/[^/]+/art-(\d+)\.html'),
            'IL': re.compile(r'/[^/]+/a/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})')}
LIMIT = 3_000_000
DECODER = json.JSONDecoder()


def article_link(source, url):
    parsed = urlsplit(url)
    match = PATTERNS[source].fullmatch(parsed.path)
    if parsed.scheme == 'https' and parsed.netloc in HOSTS[source] and match:
        return match[1], f'https://{parsed.netloc}{parsed.path}'
    return None


class PublisherRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != 'https' or not any(target.netloc in hosts for hosts in HOSTS.values()):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    request = Request(url, headers={'User-Agent': 'Uutiskeskustelu/0.1', 'Accept': 'text/html, application/rss+xml, application/xml'})
    with build_opener(PublisherRedirect()).open(request, timeout=8) as response:
        return response.geturl(), response.read(LIMIT)


def il_commenting(script, article_id):
    # The initialization script contains JavaScript after the article properties.
    # Decode just the requested article's top-level JSON properties in order.
    start = re.search(r'"articles"\s*:\s*\{\s*"' + re.escape(article_id)
                      + r'"\s*:\s*\{\s*"items"\s*:\s*\{', script)
    if not start:
        return None
    fields = {}
    position = start.end()
    while True:
        key, position = DECODER.raw_decode(script, re.match(r'\s*', script[position:]).end() + position)
        colon = re.match(r'\s*:\s*', script[position:])
        if not colon:
            return None
        value, position = DECODER.raw_decode(script, position + colon.end())
        if key in ('article_id', 'commenting_enabled'):
            fields[key] = value
        if fields.keys() >= {'article_id', 'commenting_enabled'}:
            return fields['commenting_enabled'] if fields['article_id'] == article_id else None
        separator = re.match(r'\s*,\s*', script[position:])
        if not separator:
            return None
        position += separator.end()


def commenting_status(source, article_id, raw):
    try:
        if source == 'IS':
            match = re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', raw, re.S)
            if not match:
                return None
            data = json.loads(match[1])['props']['pageProps']['page']['assetData']
            if str(data['id']) != article_id:
                return None
            visible, ended = data['commentingVisible'], data['commentingEnded']
            if type(visible) is not bool or type(ended) is not bool:
                return None
            if ended:
                return 'ended'
            return 'open' if visible else 'disabled'
        match = re.search(r'<script\b[^>]*>\s*window\.App\s*=\s*(.*?)</script>', raw, re.S)
        enabled = il_commenting(match[1], article_id) if match else None
        if type(enabled) is bool:
            return 'open' if enabled else 'disabled'
    except (ValueError, TypeError, KeyError):
        pass
    return None


def inspect(item):
    source, article_id, url, _, _ = item
    try:
        final, raw = download(url)
        link = article_link(source, final)
        if link and link[0] == article_id:
            return item, commenting_status(source, article_id, raw.decode('utf-8', 'replace'))
    except (OSError, ValueError):
        pass
    return item, None

