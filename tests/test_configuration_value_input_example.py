from decimal import Decimal
from pathlib import Path
import unittest
from test_configuration_value_input import InputFixture

ROOT = Path(__file__).resolve().parents[1]

class TypedInputExampleTests(InputFixture, unittest.TestCase):
    def loaded(self):
        folder = ROOT / 'examples/configuration-value-input'
        sources = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        _, app, _ = self.host(sources)
        owner = app.active or self.open(app)
        return app, owner

    def prompt(self, button):
        app, owner = self.loaded()
        result = self.event(app, owner, control=button)
        self.assertIsNone(result['error'], result)
        self.assertIsNone(result['form']['result']['error'], result)
        self.assertEqual(len(result['inputs']), 1, result)
        return app, owner, result['inputs'][0]

    def test_quantity_accepts_exact_decimal(self):
        app, owner, descriptor = self.prompt('QuestionButton')
        result = self.answer(app, owner, descriptor, value=Decimal('2.30'))
        self.assertIsNone(result['error'], result)
        self.assertEqual(self.greeting(app, owner), '2,3')

    def test_reason_cancel_preserves_owner_value(self):
        app, owner, descriptor = self.prompt('ReasonButton')
        prior = self.greeting(app, owner)
        result = self.answer(app, owner, descriptor, action='cancel')
        self.assertIsNone(result['error'], result)
        self.assertEqual(self.greeting(app, owner), prior)

    def test_reason_accepts_empty_not_cancel(self):
        app, owner, descriptor = self.prompt('ReasonButton')
        result = self.answer(app, owner, descriptor, value='')
        self.assertIsNone(result['error'], result)
        self.assertEqual(self.greeting(app, owner), '')
        self.assertEqual(app.sessions[owner][0].session.form._data['lastanswer'], 'Reason confirmed')

    def test_date_initial_is_typed_and_can_cancel(self):
        app, owner, descriptor = self.prompt('WarningButton')
        self.assertEqual(descriptor['value']['type'], 'Date')
        self.assertEqual(descriptor['editor'], {'kind':'date','parts':'dateTime'})
        self.assertIsNone(self.answer(app, owner, descriptor, action='cancel')['error'])

    def test_priority_retains_exact_original_item(self):
        app, owner, descriptor = self.prompt('PriorityButton')
        self.assertEqual(descriptor['initial'], descriptor['choices'][1]['choice'])
        result = self.answer(app, owner, descriptor, action='choose', choice=descriptor['initial'])
        self.assertIsNone(result['error'], result)
        self.assertEqual(self.greeting(app, owner), 'urgent')
        self.assertIn('Original second item: Да', result['form']['result']['state']['messages'])

    def test_details_stays_an_independent_owned_form(self):
        app, owner = self.loaded()
        result = self.event(app, owner, control='DetailsButton')
        self.assertIsNone(result['error'], result)
        self.assertNotEqual(app.active, owner)
        self.assertEqual(result['inputs'], [])
