"""Closed host primitives for future owned input/selection interactions.

No public BSL names, callbacks, form authority or DB operations are installed.
The application envelope must still admit the owner/family and reserve callback
delivery before executing it. These types are not a native dialog API claim.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import re
from secrets import token_hex
from weakref import ReferenceType

from .dates import BSLDate
from .form_dialogs import dialog_text
from .form_model import BSLFormAttribute, scalar
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import BSLAllowedLength
from .ui.protocol import encode_line, decode_line
from .value_lists import BSLValueList, BSLValueListItem
from .values import BSLType

MAX_CHOICES = 128
MAX_SELECTION_BYTES = 32768
MAX_PRESENTATION = 1024
_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_SCALARS = {BSLType.STRING: str, BSLType.NUMBER: Decimal,
            BSLType.BOOLEAN: bool, BSLType.DATE: BSLDate}


def _scalar_packet(value):
    """Existing private form envelope, including empty Date, not generic refs."""
    if not any(type(value) is kind for kind in (str, Decimal, bool, BSLDate)):
        raise TypeError('exact input scalar required')
    scalar(value)
    # Lazy import keeps this primitive independent of interpreter startup.
    from .form_replication import _encode_form_scalar
    return _encode_form_scalar(value)


def _exact_value(descriptor, value):
    if type(value) is not _SCALARS[descriptor.types[0]]:
        raise TypeError('input value differs from the fixed type')
    _scalar_packet(value)
    # Native AdjustValue may round, clamp, truncate or coerce. Those operations
    # must not quietly change a submitted user value. Fixed String right-padding
    # alone is admitted, matching existing form editors and their fixed flag.
    with localcontext():
        adjusted = descriptor.adjust_value(value)
    if type(value) is str:
        fixed = descriptor.string_qualifiers.allowed_length is BSLAllowedLength.FIXED
        if adjusted != value and not (fixed and adjusted.startswith(value)
                                     and adjusted[len(value):] == ' ' * (len(adjusted) - len(value))):
            raise ValueError('input would be truncated or converted')
    elif type(adjusted) is not type(value) or adjusted != value:
        raise ValueError('input would be rounded, clamped or converted')
    _scalar_packet(adjusted)
    # Preserve exact Number representation when qualification is value-lossless.
    return adjusted if type(value) is str else value


@dataclass(frozen=True, slots=True, init=False)
class ScalarInputSpec:
    """Immutable single-type intent; decode validates, never dispatches a callback.

    Undefined/Null are not scalar answers in this slice. Undefined initial uses
    the fixed descriptor's existing bounded form default, a provisional host
    binding rather than a measured native dialog rule. Cancellation belongs to
    the outer interaction protocol and cannot be disguised as an empty value.
    Public packets are detached copies; the initial image is never retained as
    mutable caller input. Descriptor/qualifier values are existing frozen types.
    """
    _descriptor: BSLTypeDescription
    _initial: bytes
    _editor: bytes

    @classmethod
    def capture(cls, descriptor, initial):
        if cls is not ScalarInputSpec or type(descriptor) is not BSLTypeDescription:
            raise TypeError('exact scalar input descriptor required')
        if descriptor._query_scalar is not None:
            raise ValueError('query descriptors are not input types')
        if (len(descriptor.types) != 1
                or not any(descriptor.types[0] is kind for kind in _SCALARS)):
            raise ValueError('one scalar input type required')
        # Reuse the existing form singleton/qualifier bounds, without allowing
        # its separate scoped-reference branch to become an input permission.
        BSLFormAttribute('Input', descriptor)
        descriptor = BSLTypeDescription(descriptor)
        if initial is None:
            with localcontext():
                initial = descriptor.adjust_value()
        value = _exact_value(descriptor, initial)
        from .ui.form_app import FormController
        editor = FormController._editor_description(descriptor)
        if descriptor.types == (BSLType.BOOLEAN,):
            editor = {'kind': 'boolean'}
        if editor is None:
            raise ValueError('unsupported scalar editor')
        initial_image, editor_image = encode_line(_scalar_packet(value)), encode_line(editor)
        result = object.__new__(cls)
        object.__setattr__(result, '_descriptor', descriptor)
        object.__setattr__(result, '_initial', initial_image)
        object.__setattr__(result, '_editor', editor_image)
        return result

    def public(self):
        return {'value': decode_line(self._initial), 'editor': decode_line(self._editor)}

    def decode(self, packet):
        """Consume only the existing scalar shape, never browser type metadata."""
        if (type(packet) is not dict or len(packet) > 2
                or any(type(key) is not str
                       or not any(type(value) is kind for kind in (str, bool))
                       for key, value in packet.items())):
            raise ValueError('exact scalar packet required')
        from .form_replication import _decode_form_scalar
        with localcontext():
            return _exact_value(self._descriptor, _decode_form_scalar(packet))


def _list_witness(source):
    """Exact current contents, not just ValueList's structural revision.

    Item field writes do not advance the existing list revision. Keep their
    bounded scalar bytes and plain presentation/check fields as well as item
    identity/order/membership. This is a current-state witness, not a history
    of intermediate field mutations that were subsequently undone.
    """
    if type(source) is not BSLValueList or type(source.items) is not list:
        raise TypeError('exact ValueList required')
    if len(source.items) > MAX_CHOICES:
        raise ValueError('selection item limit')
    if (type(source.value_type) is not BSLTypeDescription
            or source.value_type != BSLTypeDescription()
            or type(source._revision) is not int or source._revision < 0
            or type(source._by_id) is not dict or len(source._by_id) != len(source.items)):
        raise ValueError('unsupported ValueList shape or type constraints')
    rows, identities, size = [], set(), 0
    for item in source.items:
        if (type(item) is not BSLValueListItem or id(item) in identities
                or type(item._owner_ref) is not ReferenceType
                or item._owner_ref() is not source or item._detached is not False
                or item._decoded_standalone is not False
                or type(item._id) is not int or not 0 <= item._id < 2 ** 32
                or source._by_id.get(item._id) is not item or type(item.check) is not bool):
            raise ValueError('selection item ownership mismatch')
        identities.add(id(item))
        value = encode_line(_scalar_packet(item.value))
        presentation = dialog_text(item.presentation, MAX_PRESENTATION)
        size += len(value) + len(presentation.encode('utf-8'))
        if size > MAX_SELECTION_BYTES:
            raise ValueError('selection byte limit')
        rows.append((item, item._id, value, presentation, item.check))
    return source._revision, tuple(rows)


class ValueListSelection:
    """One-shot host selection retaining original items, never serialized IDs.

    Public rows use fresh opaque choice tokens. Invalid tokens leave the prompt
    pending; source drift retires it. take() reserves terminal state and releases
    all retained references before returning the exact original item. The host
    must deliver it synchronously through its existing trusted callback gate.
    """
    __slots__ = ('_source', '_witness', '_choices', '_image', '_state')

    @classmethod
    def capture(cls, source):
        if cls is not ValueListSelection:
            raise TypeError('exact host selection required')
        witness = _list_witness(source)
        choices, seen, rows = [], set(), []
        for item, _, value, presentation, _ in witness[1]:
            token = token_hex(16)
            if type(token) is not str or not _TOKEN.fullmatch(token) or token in seen:
                raise ValueError('selection choice token collision')
            seen.add(token)
            choices.append((token, item))
            rows.append({'choice': token, 'value': decode_line(value), 'presentation': presentation})
        image = encode_line({'choices': rows})
        if len(image) > MAX_SELECTION_BYTES:
            raise ValueError('selection byte limit')
        result = object.__new__(cls)
        result._source, result._witness = source, witness
        result._choices, result._image, result._state = tuple(choices), image, 'pending'
        return result

    @property
    def state(self):
        return self._state

    def _pending(self):
        if self._state != 'pending':
            raise ValueError('selection retired')

    def _retire(self, state):
        # No allocation or fallible user code after terminal reservation.
        self._state = state
        self._source = None
        self._witness = self._choices = ()
        self._image = b''

    def require_current(self):
        self._pending()
        try:
            current = _list_witness(self._source)
            previous = self._witness
            if (current[0] != previous[0] or len(current[1]) != len(previous[1])
                    or any(a[0] is not b[0] or a[1:] != b[1:] for a, b in zip(current[1], previous[1]))):
                raise ValueError('selection source changed')
        except BaseException:
            self._retire('stale')
            raise

    def public(self):
        self.require_current()
        return decode_line(self._image)

    def take(self, token):
        self._pending()
        if type(token) is not str or not _TOKEN.fullmatch(token):
            raise ValueError('invalid selection token')
        item = next((item for choice, item in self._choices if choice == token), None)
        if item is None:
            raise ValueError('unknown selection token')
        self.require_current()
        self._retire('consumed')
        return item

    def cancel(self):
        self._pending()
        self._retire('cancelled')
