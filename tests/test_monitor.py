import json
import pathlib
import tempfile
import unittest
from monitor import parse_html, process

SAMPLE = pathlib.Path(__file__).parent / 'fixtures' / 'sample.html'


class MonitorTests(unittest.TestCase):
    def test_budget_city_and_price(self):
        records, count = parse_html(SAMPLE.read_text(encoding='utf-8'), 'Чебоксары')
        self.assertEqual(count, 4)
        self.assertEqual([r['id'] for r in records], ['1001'])
        self.assertEqual(records[0]['price_rub'], 80000)
        self.assertFalse(records[0]['verified_live'])
        self.assertNotIn('?', records[0]['url'])

    def test_first_run_and_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            html = SAMPLE.read_text(encoding='utf-8')
            self.assertEqual(process(html, output), 'ok')
            first = json.loads((output / 'feed.json').read_text())
            self.assertEqual(len(first['candidates']), 1)
            self.assertEqual(len(first['new_candidates']), 1)
            process(html, output)
            second = json.loads((output / 'feed.json').read_text())
            self.assertEqual(len(second['candidates']), 1)
            self.assertEqual(second['new_candidates'], [])

    def test_failed_parse_preserves_results(self):
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory)
            self.assertEqual(process('<html>No cards</html>', output), 'no_cards')
            self.assertFalse((output / 'seen.json').exists())
            process(SAMPLE.read_text(encoding='utf-8'), output)
            previous = (output / 'feed.json').read_bytes()
            self.assertEqual(process('<html>No cards</html>', output), 'no_cards')
            self.assertEqual((output / 'feed.json').read_bytes(), previous)


if __name__ == '__main__':
    unittest.main()
