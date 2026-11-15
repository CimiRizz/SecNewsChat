"""Kustantajien Luetuimmat-listat ja kommentointitilan tarkistus."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from keraaja import article_link, download, inspect

PUBLISHER_LISTS = {
    'IS': 'https://www.is.fi/api/laneitems/553251/list?listTemplate=teaser-xs',
    'IL': 'https://www.iltalehti.fi/luetuimmat',
}
IL_LIST = re.compile(r'"mostRead"\s*:\s*\{\s*"c:,fe:coma-mostread,50"\s*:\s*\{\s*"items"\s*:\s*')
CLOSED = ('disabled', 'ended')


def ranked_articles(source, raw):
    if source == 'IS':
        items = json.loads(raw)
    else:
        marker = IL_LIST.search(raw)
        if not marker:
            raise ValueError('IL:n Luetuimmat-listaa ei löytynyt')
        items = json.JSONDecoder().raw_decode(raw, marker.end())[0]
    if not isinstance(items, list):
        raise ValueError('Luetuimmat-listan muoto muuttui')

    seen = set()
    for rank, article in enumerate(items, 1):
        if source == 'IS':
            href = article.get('href')
            title = article.get('title')
            date = article.get('displayDate')
        else:
            article_id = article.get('article_id')
            category = (article.get('category') or {}).get('category_name')
            href = f'/{category}/a/{article_id}' if category and article_id else None
            title = article.get('headline') or article.get('title')
            date = article.get('published_at')
        if not isinstance(href, str) or not isinstance(title, str) or not title.strip():
            continue
        link = article_link(source, urljoin(PUBLISHER_LISTS[source], href))
        if link and link[0] not in seen:
            seen.add(link[0])
            yield rank, (source, *link, ' '.join(title.split()), date or '')


def check_ranked(source):
    _, body = download(PUBLISHER_LISTS[source])
    candidates = list(ranked_articles(source, body.decode('utf-8')))
    if not candidates:
        raise ValueError('Luetuimmat-lista oli tyhjä')
    with ThreadPoolExecutor(max_workers=6) as pool:
        checks = pool.map(inspect, (item for _, item in candidates))
        results = [(rank, item, status) for (rank, _), (item, status) in zip(candidates, checks)]
    return results
