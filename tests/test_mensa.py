from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
import unittest

from mensa import MenuUnavailable, fetch_menu, parse_menu


HTML = (Path(__file__).parent / 'fixtures' / 'mensa.html').read_text(encoding='utf-8')
DAY = date(2026, 10, 15)


class MenuTests(unittest.TestCase):
    def test_exact_day_names_only_with_soup_and_side_dishes_separated(self):
        menu = parse_menu(HTML, DAY)
        self.assertEqual(menu.day, DAY)
        self.assertEqual(menu.mains, ('Gemüse & Reis mit Soße', 'Tagessuppe'))
        self.assertEqual(menu.sides, ('Reis', 'Grünes Gemüse', 'Pudding'))

    def test_other_dates_do_not_leak_into_the_result(self):
        menu = parse_menu(HTML, date(2026, 10, 16))
        self.assertEqual(menu.mains, ("Tomorrow's dish",))
        self.assertEqual(menu.sides, ())

    def test_missing_day_and_closed_day_are_unavailable(self):
        for day in (date(2026, 10, 17), date(2026, 10, 18)):
            with self.subTest(day=day), self.assertRaises(MenuUnavailable):
                parse_menu(HTML, day)

    def test_wrong_canteen_and_unrecognised_page_are_rejected(self):
        for html in (HTML.replace('selected value=13', 'selected value=18'),
                     HTML.replace('id=menuContainer', 'id=other'), '<h1>Maintenance</h1>'):
            with self.subTest(html=html[:40]), self.assertRaises(MenuUnavailable):
                parse_menu(html, DAY)

    @patch('mensa.urlopen', side_effect=URLError('offline'))
    def test_network_failure_is_reported_as_unavailable(self, urlopen):
        with self.assertRaisesRegex(MenuUnavailable, 'offline'):
            fetch_menu(DAY)


if __name__ == '__main__':
    unittest.main()
