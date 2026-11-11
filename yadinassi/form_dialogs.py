"""Closed, host-lifetime dialog values and receipts. No browser callbacks."""
from dataclasses import dataclass
from enum import Enum

from .values import BSLObject

DIALOG_CAPABILITY = 'yadinassi-owned-dialog/1'
MAX_DIALOGS = 256
MAX_DIALOG_TEXT = 4096
MAX_DIALOG_TITLE = 256


class QuestionDialogMode(Enum):
    OK = ('ok',)
    OK_CANCEL = ('ok', 'cancel')
    YES_NO = ('yes', 'no')
    YES_NO_CANCEL = ('yes', 'no', 'cancel')

    def __str__(self):
        raise ValueError('dialog mode presentation is outside the host profile')


class DialogReturnCode(Enum):
    OK = 'ok'
    CANCEL = 'cancel'
    YES = 'yes'
    NO = 'no'

    def __str__(self):
        raise ValueError('dialog return presentation is outside the host profile')


class _QuestionModes(BSLObject):
    def __str__(self):
        raise ValueError('dialog namespace presentation is outside the host profile')

    def get_member(self, name):
        values = {'ok': QuestionDialogMode.OK, 'ок': QuestionDialogMode.OK,
                  'okcancel': QuestionDialogMode.OK_CANCEL, 'окотмена': QuestionDialogMode.OK_CANCEL,
                  'yesno': QuestionDialogMode.YES_NO, 'данет': QuestionDialogMode.YES_NO,
                  'yesnocancel': QuestionDialogMode.YES_NO_CANCEL, 'данетотмена': QuestionDialogMode.YES_NO_CANCEL}
        return values[name.casefold()] if name.casefold() in values else super().get_member(name)


class _ReturnCodes(BSLObject):
    def __str__(self):
        raise ValueError('dialog namespace presentation is outside the host profile')

    def get_member(self, name):
        values = {'ok': DialogReturnCode.OK, 'ок': DialogReturnCode.OK,
                  'cancel': DialogReturnCode.CANCEL, 'отмена': DialogReturnCode.CANCEL,
                  'yes': DialogReturnCode.YES, 'да': DialogReturnCode.YES,
                  'no': DialogReturnCode.NO, 'нет': DialogReturnCode.NO}
        return values[name.casefold()] if name.casefold() in values else super().get_member(name)


QUESTION_DIALOG_MODES = _QuestionModes()
DIALOG_RETURN_CODES = _ReturnCodes()


def dialog_text(value, limit):
    if type(value) is not str or len(value) > limit:
        raise ValueError('bounded plain dialog text required')
    # Admit Unicode, not host control strings or invalid surrogate sequences.
    value.encode('utf-8')
    if any(ord(char) < 32 and char not in '\n\r\t' for char in value):
        raise ValueError('dialog control character')
    return value


@dataclass(slots=True)
class OwnedDialog:
    ticket: str
    owner: str
    callback: object
    enrollment: object
    generation: int
    kind: str
    title: str
    text: str
    choices: tuple
    state: str = 'queued'
    result: object = None

    def public(self):
        return {'ticket': self.ticket, 'owner': self.owner, 'kind': self.kind,
                'title': self.title, 'text': self.text, 'choices': list(self.choices)}

    def finish(self, state):
        self.state = state
        self.callback = self.enrollment = self.result = None
        self.title = self.text = ''
        self.choices = ()
