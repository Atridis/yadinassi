"""Реальный host/BSL сценарий черновика, без записи БД и claims native parity."""
from decimal import Decimal
import unittest
from test_configuration_dialogs import DialogFixture
from main_demo_interactions_fixture import sources
from yadinassi.ui.protocol import encode_value


class OperationDraftTests(DialogFixture, unittest.TestCase):
    def setup_draft(self):
        _, app, _ = self.host(sources())
        owner = self.open(app, 'CommonForm.OperationDraft')
        self.event(app, owner, 'EditButton')
        child = app.active
        self.assertNotEqual(owner, child)
        return app, owner, child

    def data(self, app, sid):
        return app.sessions[sid][0].session.form._data

    def prepare(self, app, owner, child):
        self.event(app, child, 'AmountField', event='change', value=encode_value(Decimal('123.45')))
        self.event(app, child, 'CommentField', event='change', value=encode_value('Поставка'))
        self.assertEqual(self.data(app, owner)['amount'], Decimal(0))
        result = self.event(app, child, 'AcceptButton')
        self.assertIsNone(result['error'], result)
        self.assertEqual(self.data(app, owner)['amount'], Decimal(0))
        self.assertNotIn(child, app.sessions)

    def question(self, app, owner, answer):
        result = self.event(app, owner, 'ConfirmButton')
        self.assertIsNone(result['error'], result)
        dialog = result['dialogs'][0]
        response = self.answer(app, owner, dialog, answer)
        self.assertIsNone(response['error'], response)
        return dialog

    def test_yes_applies_once_and_old_ticket_cannot_repeat(self):
        app, owner, child = self.setup_draft(); self.prepare(app, owner, child)
        dialog = self.question(app, owner, 'yes')
        self.assertEqual(self.data(app, owner)['amount'], Decimal('123.45'))
        self.assertEqual(self.data(app, owner)['comment'], 'Поставка')
        self.assertEqual(self.data(app, owner)['appliedcount'], 1)
        self.assertIsNotNone(self.answer(app, owner, dialog, 'yes')['error'])
        result = self.event(app, owner, 'ConfirmButton')
        self.assertEqual(result['dialogs'], [])
        self.assertEqual(self.data(app, owner)['appliedcount'], 1)

    def test_no_discards_prepared_values(self):
        app, owner, child = self.setup_draft(); self.prepare(app, owner, child)
        self.question(app, owner, 'no')
        self.assertEqual(self.data(app, owner)['amount'], 0)
        self.assertEqual(self.event(app, owner, 'ConfirmButton')['dialogs'], [])
        self.assertEqual(self.data(app, owner)['appliedcount'], 0)

    def test_cancel_keeps_prepared_values_for_later_confirmation(self):
        app, owner, child = self.setup_draft(); self.prepare(app, owner, child)
        self.question(app, owner, 'cancel')
        self.assertEqual(self.data(app, owner)['amount'], 0)
        self.question(app, owner, 'yes')
        self.assertEqual(self.data(app, owner)['amount'], Decimal('123.45'))
        self.assertEqual(self.data(app, owner)['appliedcount'], 1)

    def test_child_cancel_leaves_owner_unchanged(self):
        app, owner, child = self.setup_draft()
        self.event(app, child, 'AmountField', event='change', value=encode_value(Decimal(99)))
        self.event(app, child, 'CancelButton')
        self.assertNotIn(child, app.sessions)
        self.assertEqual(self.data(app, owner)['amount'], 0)
        self.assertEqual(self.event(app, owner, 'ConfirmButton')['dialogs'], [])

    def test_keep_open_veto_does_not_deliver_result(self):
        app, owner, child = self.setup_draft()
        self.event(app, child, 'KeepOpenField', event='change', value=encode_value(True))
        self.event(app, child, 'AcceptButton')
        self.assertIn(child, app.sessions)
        self.assertEqual(self.data(app, owner)['appliedcount'], 0)
        self.event(app, child, 'CancelButton')
        self.assertIn(child, app.sessions)
        self.event(app, child, 'KeepOpenField', event='change', value=encode_value(False))
        self.event(app, child, 'CancelButton')
        self.assertNotIn(child, app.sessions)

    def test_message_box_preserves_business_fields(self):
        app, owner, child = self.setup_draft(); self.prepare(app, owner, child)
        self.question(app, owner, 'yes')
        before = {k:self.data(app, owner)[k] for k in ('drafttitle','amount','comment','appliedcount')}
        result = self.event(app, owner, 'InfoButton')
        dialog = result['dialogs'][0]
        response = self.answer(app, owner, dialog, 'dismiss')
        self.assertIsNone(response['error'], response)
        self.assertEqual(before, {k:self.data(app, owner)[k] for k in before})

    def test_reopen_prepared_draft_cancel_preserves_prior_snapshot(self):
        app, owner, child = self.setup_draft(); self.prepare(app, owner, child)
        self.question(app, owner, 'cancel')
        result = self.event(app, owner, 'EditButton')
        self.assertIsNone(result['error'], result)
        reopened = app.active
        self.assertNotEqual(reopened, owner)
        self.assertEqual(self.data(app, reopened)['amount'], Decimal('123.45'))
        self.assertEqual(self.data(app, reopened)['comment'], 'Поставка')
        self.event(app, reopened, 'AmountField', event='change', value=encode_value(Decimal(99)))
        self.event(app, reopened, 'CancelButton')
        self.assertNotIn(reopened, app.sessions)
        self.assertEqual(self.data(app, owner)['amount'], 0)
        self.question(app, owner, 'yes')
        self.assertEqual(self.data(app, owner)['amount'], Decimal('123.45'))
        self.assertEqual(self.data(app, owner)['appliedcount'], 1)
