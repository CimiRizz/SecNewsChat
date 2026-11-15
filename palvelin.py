"""Uutiskeskustelu – Python 3.10+ ja SQLite."""
import hmac
import json
import os
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from luetuimmat import CLOSED, PUBLISHER_LISTS, check_ranked

ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get('DATABASE_PATH', ROOT / 'keskustelu.sqlite3'))
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '')
REFRESH_SECONDS = 600


@contextmanager
def database():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, publisher_id TEXT NOT NULL,
                url TEXT NOT NULL, title TEXT NOT NULL, published INTEGER NOT NULL,
                status TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0,
                UNIQUE(source, publisher_id)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES articles(id),
                author TEXT NOT NULL, body TEXT NOT NULL, created INTEGER NOT NULL,
                removed INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS messages_thread ON messages(article_id, id);
            CREATE TABLE IF NOT EXISTS rankings (
                article_id INTEGER PRIMARY KEY REFERENCES articles(id), rank INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ranking_updates (
                source TEXT PRIMARY KEY, checked INTEGER, status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                message_id INTEGER PRIMARY KEY REFERENCES messages(id), created INTEGER NOT NULL
            );
        """)


def article_values(item, status):
    source, publisher_id, url, title, date = item
    try:
        try:
            published = datetime.fromisoformat(date)
        except ValueError:
            published = parsedate_to_datetime(date)
        stamp = int((published if published.tzinfo else published.replace(tzinfo=timezone.utc)).timestamp())
    except (ValueError, TypeError, OverflowError):
        stamp = int(time.time())
    return source, publisher_id, url, title[:500], stamp, status


def refresh_source(source):
    results = check_ranked(source)
    if not any(status for _, _, status in results):
        raise ValueError('Kommentointitiloja ei saatu tarkistettua')
    partial = any(status is None for _, _, status in results)
    with database() as db:
        db.execute('DELETE FROM rankings WHERE article_id IN (SELECT id FROM articles WHERE source=?)', (source,))
        for rank, item, status in results:
            if status is None:
                continue
            if status in CLOSED:
                db.execute("""INSERT INTO articles (source,publisher_id,url,title,published,status)
                              VALUES (?,?,?,?,?,?) ON CONFLICT(source,publisher_id) DO UPDATE SET
                              url=excluded.url,title=excluded.title,published=excluded.published,status=excluded.status""",
                           article_values(item, status))
                db.execute("""INSERT INTO rankings(article_id,rank)
                              SELECT id,? FROM articles WHERE source=? AND publisher_id=?""",
                           (rank, source, item[1]))
            else:
                db.execute('UPDATE articles SET status=? WHERE source=? AND publisher_id=?', (status, source, item[1]))
        db.execute("""INSERT INTO ranking_updates VALUES (?,?,?)
                      ON CONFLICT(source) DO UPDATE SET checked=excluded.checked,status=excluded.status""",
                   (source, int(time.time()), 'partial' if partial else 'ok'))


def collector():
    while True:
        start = time.monotonic()
        for source in PUBLISHER_LISTS:
            try:
                refresh_source(source)
            except Exception as error:
                print(f'{source}: Luetuimmat-haku epäonnistui ({type(error).__name__})', flush=True)
                with database() as db:
                    db.execute("""INSERT INTO ranking_updates VALUES (?,NULL,'error')
                                  ON CONFLICT(source) DO UPDATE SET status='error'""", (source,))
        time.sleep(max(0, REFRESH_SECONDS - (time.monotonic() - start)))


def top_threads(db):
    rows = db.execute("""SELECT a.id, a.title, a.source, a.published, a.locked, a.status, r.rank,
                 (SELECT COUNT(*) FROM messages m WHERE m.article_id=a.id AND m.removed=0) AS replies
                 FROM rankings r JOIN articles a ON a.id=r.article_id
                 WHERE a.status IN ('disabled','ended')
                 ORDER BY r.rank, a.source DESC, a.id""")
    threads = []
    seen_titles = set()
    for row in rows:
        title_key = ''.join(c for c in unicodedata.normalize('NFKC', row['title']).casefold() if c.isalnum())
        if title_key and title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        threads.append(dict(row))
        if len(threads) == 10:
            break
    sources = {row['source']: dict(row) for row in db.execute('SELECT * FROM ranking_updates')}
    return {'threads': threads, 'sources': sources}


ASSETS = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
          '/style.css': ('style.css', 'text/css')}
BANNER_PATHS = {f'/{device}/mainokset/{slot}.webp'
                for device in ('tietokone', 'mobiili')
                for slot in ('top', 'after-5', 'after-10')}
write_lock = threading.Lock()
recent_writes = {}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload, mime='application/json'):
        data = json.dumps(payload, ensure_ascii=False).encode() if mime == 'application/json' else payload
        self.send_response(status)
        self.send_header('Content-Type', mime if mime.startswith('image/') else f'{mime}; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, message):
        self.respond(status, {'error': message})

    def admin(self):
        supplied = self.headers.get('Authorization', '').encode()
        return bool(ADMIN_TOKEN) and hmac.compare_digest(supplied, ('Bearer ' + ADMIN_TOKEN).encode())

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ASSETS:
            name, mime = ASSETS[path]
            return self.respond(200, (ROOT / name).read_bytes(), mime)
        if path in BANNER_PATHS:
            try:
                data = (ROOT / path.lstrip('/')).read_bytes()
            except FileNotFoundError:
                return self.error(404, 'Mainosbanneria ei löytynyt.')
            return self.respond(200, data, 'image/webp')
        if path == '/health':
            return self.respond(200, {'ok': True})
        with database() as db:
            if path == '/api/threads':
                return self.respond(200, top_threads(db))
            if path.startswith('/api/threads/'):
                thread_id = path.removeprefix('/api/threads/')
                article = db.execute("SELECT id,title,source,url,published,locked FROM articles WHERE id=? AND status IN ('disabled','ended')",
                                     (thread_id,)).fetchone()
                if article:
                    rows = db.execute("""SELECT id,author,body,created FROM
                        (SELECT id,author,body,created FROM messages WHERE article_id=? AND removed=0
                         ORDER BY id DESC LIMIT 200) ORDER BY id""", (article['id'],))
                    return self.respond(200, {**dict(article), 'messages': [dict(row) for row in rows]})
            if path == '/api/reports':
                if not self.admin():
                    return self.error(401, 'Anna ylläpitäjän avain.')
                rows = db.execute("""SELECT m.id,m.article_id,m.author,m.body,a.title FROM reports r
                    JOIN messages m ON m.id=r.message_id JOIN articles a ON a.id=m.article_id
                    WHERE m.removed=0 ORDER BY r.created DESC LIMIT 100""")
                return self.respond(200, [dict(row) for row in rows])
        self.error(404, 'Sivua ei löytynyt.')

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/messages', '/api/report', '/api/moderate'):
            return self.error(404, 'Toimintoa ei löytynyt.')
        if path == '/api/moderate' and not self.admin():
            return self.error(401, 'Anna ylläpitäjän avain.')
        if self.headers.get_content_type() != 'application/json':
            return self.error(415, 'Pyyntö on väärässä muodossa.')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 16000:
                return self.error(413, 'Pyyntö on liian pitkä tai tyhjä.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError
            item_id = data.get('id')
            if type(item_id) is not int or not 0 < item_id < 2**63:
                raise ValueError
        except (ValueError, UnicodeError):
            return self.error(400, 'Tarkista lähettämäsi tiedot.')
        if path != '/api/moderate':
            ip = self.client_address[0]
            if os.environ.get('RENDER'):
                ip = self.headers.get('X-Forwarded-For', ip).split(',')[-1].strip()
            key = (ip, path)
            now = time.monotonic()
            with write_lock:
                for old in list(recent_writes):
                    if now - recent_writes[old] > 10:
                        del recent_writes[old]
                if key in recent_writes:
                    return self.error(429, 'Odota hetki ennen uutta lähetystä.')
                recent_writes[key] = now
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            if path == '/api/messages':
                author, body = data.get('author'), data.get('body')
                if not isinstance(author, str) or not isinstance(body, str):
                    return self.error(400, 'Anna nimimerkki ja viesti.')
                author, body = ' '.join(author.split()), body.strip()
                if not 1 <= len(author) <= 32 or not 1 <= len(body) <= 3000:
                    return self.error(400, 'Nimimerkki voi olla 1–32 ja viesti 1–3000 merkkiä.')
                row = db.execute("SELECT locked FROM articles WHERE id=? AND status IN ('disabled','ended')", (item_id,)).fetchone()
                if not row:
                    return self.error(404, 'Ketjua ei löytynyt.')
                if row['locked']:
                    return self.error(409, 'Ketju on lukittu.')
                db.execute('INSERT INTO messages(article_id,author,body,created) VALUES (?,?,?,?)',
                           (item_id, author, body, int(time.time())))
            elif path == '/api/report':
                if not db.execute('SELECT 1 FROM messages WHERE id=? AND removed=0', (item_id,)).fetchone():
                    return self.error(404, 'Viestiä ei löytynyt.')
                db.execute('INSERT OR IGNORE INTO reports(message_id,created) VALUES (?,?)', (item_id, int(time.time())))
            else:
                action = data.get('action')
                if action == 'remove':
                    result = db.execute('UPDATE messages SET removed=1 WHERE id=?', (item_id,))
                elif action in ('lock', 'unlock'):
                    result = db.execute("UPDATE articles SET locked=? WHERE id=? AND status IN ('disabled','ended')",
                                        (action == 'lock', item_id))
                else:
                    return self.error(400, 'Tuntematon toiminto.')
                if not result.rowcount:
                    return self.error(404, 'Kohdetta ei löytynyt.')
        self.respond(200, {'ok': True})


if __name__ == '__main__':
    initialize()
    threading.Thread(target=collector, daemon=True).start()
    port = int(os.environ.get('PORT', '8780'))
    print(f'Uutiskeskustelu: http://localhost:{port}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
