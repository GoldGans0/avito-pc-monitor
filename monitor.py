"""Parse supplied HTML locally. Network collection is deliberately disabled."""
import argparse
import datetime
import json
import pathlib
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.card = None
        self.root_depth = 0
        self.results = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in VOID:
            self.stack.append((tag, attrs))
        if attrs.get('data-marker') == 'item' and self.card is None:
            self.card = {'href': '', 'title': '', 'title_text': '', 'price_text': ''}
            self.root_depth = len(self.stack)
        if self.card is not None and tag == 'a':
            href = attrs.get('href', '')
            if re.search(r'_\d+(?:\?|$)', href) and not self.card['href']:
                self.card['href'] = href
                self.card['title'] = attrs.get('title', '')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.card is None:
            return
        if any(a.get('data-marker') == 'item-price' for _, a in self.stack):
            self.card['price_text'] += data
        if any(t == 'a' and a.get('href') == self.card['href'] for t, a in self.stack):
            self.card['title_text'] += data

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if self.card is not None and i < self.root_depth:
                    self.results.append(self.card)
                    self.card = None
                del self.stack[i:]
                break


def parse_html(html, city, maximum=80000):
    parser = Cards()
    parser.feed(html)
    parser.close()
    raw_count = len(parser.results)
    records = {}
    for card in parser.results:
        link = urlsplit(card['href'])
        if link.scheme or link.netloc or not link.path.startswith('/'):
            continue
        # Reject results from another city, even when the page contains recommendations.
        if not link.path.startswith('/cheboksary/'):
            continue
        identifier = re.search(r'_(\d+)$', link.path)
        price = re.search(r'([\d\s\u00a0\u202f]+)\s*₽', card['price_text'])
        if not identifier or not price:
            continue
        price = int(re.sub(r'\D', '', price.group(1)))
        title = ' '.join((card['title'] or card['title_text']).split())
        if not title or not 0 < price <= maximum:
            continue
        records[identifier[1]] = {'id': identifier[1], 'city': city,
                                 'title': title[:200], 'price_rub': price,
                                 'url': 'https://www.avito.ru' + link.path,
                                 'verified_live': False}
    return list(records.values()), raw_count


def process(html, output, city='Чебоксары'):
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=True)
    seenfile = output / 'seen.json'
    first = not seenfile.exists()
    seen = set(json.loads(seenfile.read_text(encoding='utf-8'))) if not first else set()
    records, count = parse_html(html, city)
    state = 'ok' if count else 'no_cards'
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fresh = [r for r in records if r['id'] not in seen]
    # Failed parsing does not create a baseline or erase the last successful feed.
    if state == 'ok':
        seen.update(r['id'] for r in records)
        payloads = {'seen.json': sorted(seen),
                    'feed.json': {'updated_utc': now, 'source': 'supplied_html',
                                  'first_run': first, 'candidates': records,
                                  'new_candidates': fresh, 'verified_live': False}}
    else:
        payloads = {}
    payloads['status.json'] = {'checked_utc': now, 'state': state,
                              'source': 'supplied_html', 'first_run': first,
                              'parsed_cards': count, 'matching_cards': len(records),
                              'new_count': len(fresh), 'verified_live': False}
    for name, value in payloads.items():
        temp = output / (name + '.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(output / name)
    return state


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--html', type=pathlib.Path, required=True, help='Supplied HTML file; no network request')
    cli.add_argument('--output', type=pathlib.Path, default=pathlib.Path('data'))
    args = cli.parse_args()
    try:
        state = process(args.html.read_text(encoding='utf-8'), args.output)
    except (OSError, ValueError) as exc:
        print('Input/state error: ' + type(exc).__name__)
        return 2
    print('Parse state: ' + state + '; live listings are not verified')
    return 0 if state == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
