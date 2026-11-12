"""Pure detached presentation pages, never a database reader or root service."""
import unittest
from unittest.mock import patch

from yadinassi.ui.report_pages import ReportPages, ReportPageError


def projection(count=1, text='value'):
    return {'report': 'StockStatement', 'view': 'BalanceAndTurnovers',
        'at': None, 'start': '2026-11-01T00:00:00', 'end': '2026-11-30T23:59:59',
        'periodicity': 'Month', 'columns': [{'name': 'Product', 'type': 'Catalog'}],
        'rows': [[{'type': 'Catalog', 'text': text + str(index)}] for index in range(count)]}


class InventoryReportPagesTests(unittest.TestCase):
    def setUp(self):
        self.pages = ReportPages()

    def test_empty_result_is_one_complete_page(self):
        page = self.pages.install(projection(0))
        self.assertEqual(page['rows'], [])
        self.assertEqual(page['page']['total'], 0)
        self.assertIsNone(page['page']['previous'])
        self.assertIsNone(page['page']['next'])

    def test_order_complete_and_previous_cursor_is_idempotent(self):
        original = projection(121)
        page = first = self.pages.install(original)
        rows, offsets = [], []
        while True:
            rows.extend(page['rows']); offsets.append(page['page']['offset'])
            if page['page']['next'] is None: break
            page = self.pages.read(page['page']['snapshot'], page['page']['next'])
        self.assertEqual(rows, original['rows'])
        self.assertEqual(offsets, [0, 50, 100])
        previous = self.pages.read(page['page']['snapshot'], page['page']['previous'])
        self.assertEqual(previous['page']['offset'], 50)
        self.assertEqual(self.pages.read(first['page']['snapshot'], first['page']['cursor']), first)

    def test_original_period_and_columns_are_on_every_page(self):
        page = self.pages.install(projection(51))
        second = self.pages.read(page['page']['snapshot'], page['page']['next'])
        for key in ('report', 'view', 'start', 'end', 'periodicity', 'columns'):
            self.assertEqual(page[key], second[key])

    def test_multibyte_budget_pages_without_truncating_rows(self):
        original = projection(50, '界' * 1000)
        page = self.pages.install(original)
        self.assertLess(len(page['rows']), 50)
        rows = []
        while True:
            rows.extend(page['rows'])
            if page['page']['next'] is None: break
            page = self.pages.read(page['page']['snapshot'], page['page']['next'])
        self.assertEqual(rows, original['rows'])

    def test_input_mutation_cannot_change_retained_snapshot(self):
        original = projection(51)
        first = self.pages.install(original)
        original['rows'][50][0]['text'] = 'changed'
        original['columns'][0]['name'] = 'changed'
        second = self.pages.read(first['page']['snapshot'], first['page']['next'])
        self.assertEqual(second['rows'][0][0]['text'], 'value50')
        self.assertEqual(second['columns'][0]['name'], 'Product')

    def test_return_mutation_cannot_change_retained_snapshot(self):
        page = self.pages.install(projection())
        snapshot, cursor = page['page']['snapshot'], page['page']['cursor']
        page['rows'][0][0]['text'] = 'changed'
        page['columns'].clear()
        reread = self.pages.read(snapshot, cursor)
        self.assertEqual(reread['rows'][0][0]['text'], 'value0')
        self.assertEqual(len(reread['columns']), 1)

    def test_clear_retires_old_cursor(self):
        old = self.pages.install(projection())['page']
        self.pages.clear()
        self.assertFalse(self.pages.active)
        with self.assertRaises(ReportPageError): self.pages.read(old['snapshot'], old['cursor'])

    def test_replacement_never_retargets_previous_snapshot(self):
        old = self.pages.install(projection())['page']
        fresh = self.pages.install(projection())['page']
        self.assertNotEqual(old['snapshot'], fresh['snapshot'])
        with self.assertRaises(ReportPageError): self.pages.read(old['snapshot'], fresh['cursor'])
        with self.assertRaises(ReportPageError): self.pages.read(fresh['snapshot'], old['cursor'])

    def test_same_random_cursor_still_cannot_retarget_retired_generation(self):
        with patch('yadinassi.ui.report_pages.secrets.token_urlsafe', return_value='fixed'):
            old = self.pages.install(projection())['page']
            fresh = self.pages.install(projection())['page']
        self.assertEqual(old['cursor'], fresh['cursor'])
        self.assertNotEqual(old['snapshot'], fresh['snapshot'])
        with self.assertRaises(ReportPageError): self.pages.read(old['snapshot'], old['cursor'])

    def test_failed_refresh_retires_previous_snapshot(self):
        old = self.pages.install(projection())['page']
        with self.assertRaises(ReportPageError): self.pages.install({'rows': []})
        with self.assertRaises(ReportPageError): self.pages.read(old['snapshot'], old['cursor'])

    def test_foreign_owner_or_arbitrary_cursor_refused(self):
        old = self.pages.install(projection())['page']
        other = ReportPages(); other.install(projection())
        for snapshot, cursor in ((old['snapshot'], old['cursor']), ('report-other', old['cursor'])):
            with self.assertRaises(ReportPageError): other.read(snapshot, cursor)
        for value in (None, 0, [], {}, old['cursor'] + 'x'):
            with self.assertRaises(ReportPageError): self.pages.read(old['snapshot'], value)

    def test_oversized_row_refuses_whole_snapshot(self):
        with self.assertRaises(ReportPageError): self.pages.install(projection(1, 'x' * 65536))
        self.assertFalse(self.pages.active)

    def test_oversized_header_refused(self):
        data = projection(); data['report'] = 'x' * 16385
        with self.assertRaises(ReportPageError): self.pages.install(data)

    def test_snapshot_byte_limit_refused(self):
        with patch('yadinassi.ui.report_pages.MAX_SNAPSHOT_BYTES', 500):
            with self.assertRaises(ReportPageError): self.pages.install(projection(100))

    def test_row_and_cell_limits_refused(self):
        with self.assertRaises(ReportPageError): self.pages.install(projection(1001))
        data = projection(1000)
        data['columns'] *= 26
        data['rows'] = [row * 26 for row in data['rows']]
        with self.assertRaises(ReportPageError): self.pages.install(data)

    def test_invalid_shape_or_reserved_page_field_refused(self):
        for key, value in (('rows', ()), ('columns', []), ('rows', [[]]), ('page', {})):
            data = projection(); data[key] = value
            with self.subTest(key=key), self.assertRaises(ReportPageError): self.pages.install(data)

    def test_non_json_or_nonfinite_projection_refused(self):
        for value in (float('nan'), float('inf'), b'bytes', object(), '\ud800'):
            data = projection(); data['rows'][0][0]['text'] = value
            with self.subTest(type=type(value)), self.assertRaises(ReportPageError): self.pages.install(data)

    def test_duplicate_current_page_tokens_refuse_instead_of_aliasing(self):
        with patch('yadinassi.ui.report_pages.secrets.token_urlsafe', return_value='same'):
            with self.assertRaises(ReportPageError): self.pages.install(projection(51))
        self.assertFalse(self.pages.active)
