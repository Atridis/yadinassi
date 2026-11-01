"""Immutable measured Document tabular sections, native 41263661105.

Physical row binding is performed separately on one bounded CONFIG/PARAMS graph.
No public mutation, sorting, Unload or generic composite-type admission.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from uuid import UUID
from .catalogs import CatalogCardField
from .catalog_types import BSLCatalogReference
from .values import BSLObject, HostFunction


@dataclass(frozen=True,slots=True,eq=False)
class BSLDocumentLinesType(BSLObject):
    document_uuid: UUID
    section_uuid: UUID
    generated_type_uuid: UUID
    document_name: str
    section_name: str
    snapshot: object
    family: str

    def __post_init__(self):
        if (type(self.family) is not str or self.family not in ('section','row')
                or any(type(v) is not UUID or not v.int for v in (self.document_uuid,self.section_uuid,self.generated_type_uuid))
                or any(type(v) is not str or not 1<=len(v)<=256 for v in (self.document_name,self.section_name))):
            raise ValueError('invalid document tabular-section type')
    def __eq__(self,other):
        return (type(other) is BSLDocumentLinesType and self.snapshot is other.snapshot
                and self.document_uuid==other.document_uuid and self.section_uuid==other.section_uuid
                and self.generated_type_uuid==other.generated_type_uuid and self.family==other.family)
    def __hash__(self):
        return hash((id(self.snapshot),self.document_uuid,self.section_uuid,self.generated_type_uuid,self.family))
    def __str__(self):
        return ('Документ табличная часть: ' if self.family=='section' else 'Документ табличная часть строка: ')+self.section_name


@dataclass(frozen=True, slots=True)
class DocumentLineScope:
    document_metadata_uuid: UUID
    section_metadata_uuid: UUID
    owner_uuid: UUID
    snapshot: object

    def __post_init__(self):
        for value in (self.document_metadata_uuid, self.section_metadata_uuid, self.owner_uuid):
            if type(value) is not UUID:
                raise TypeError('line identity requires UUID')
        if not self.document_metadata_uuid.int or not self.section_metadata_uuid.int:
            raise ValueError('line metadata identity cannot be empty')
        if self.document_metadata_uuid == self.section_metadata_uuid:
            raise ValueError('section and document metadata identities must differ')


@dataclass(frozen=True, slots=True)
class DocumentLineValues:
    owner_uuid: UUID
    line_number: int
    values: tuple


@dataclass(frozen=True, slots=True, eq=False)
class BSLDocumentLine(BSLObject):
    """Immutable logical row; no synthetic UUID or native row identity claim."""
    _section: object
    _line_number: int
    _values: tuple

    def get_member(self, name):
        key = name.casefold()
        if key in ('linenumber', 'номерстроки'):
            return Decimal(self._line_number)
        index = self._section._column_index(name)
        return self._values[index]

    def set_member(self, name, value):
        raise ValueError('document tabular-section rows are read-only')

    def __str__(self):
        raise ValueError('document tabular-section row presentation is not admitted')


class BSLDocumentLines(BSLObject):
    """Read-only bounded collection with independently verified owner binding."""
    def __init__(self, scope, columns, rows, catalogs, *, value_type=None, row_type=None):
        if type(scope) is not DocumentLineScope or type(columns) is not tuple or type(rows) is not tuple:
            raise TypeError('invalid document line snapshot')
        if not 1 <= len(columns) <= 10 or len(rows) > 4096:
            raise ValueError('document line snapshot exceeds bounded profile')
        names = set()
        for column in columns:
            if type(column) is not CatalogCardField or column.kind not in ('string','number','catalog_ref'):
                raise TypeError('unsupported document line column')
            key = column.name.casefold()
            if key in names or key in ('linenumber','номерстроки'):
                raise ValueError('ambiguous document line column')
            names.add(key)
        if value_type is not None or row_type is not None:
            for descriptor,family in ((value_type,'section'),(row_type,'row')):
                if (type(descriptor) is not BSLDocumentLinesType or descriptor.family!=family
                        or descriptor.document_uuid!=scope.document_metadata_uuid
                        or descriptor.section_uuid!=scope.section_metadata_uuid
                        or descriptor.snapshot is not scope.snapshot):
                    raise ValueError('document line type identity does not match scope')
        self._value_type, self._row_type = value_type, row_type
        self._scope, self._columns = scope, columns
        self._names = tuple(column.name.casefold() for column in columns)
        ordered, line_numbers = [], set()
        for row in rows:
            if (type(row) is not DocumentLineValues or type(row.owner_uuid) is not UUID
                    or row.owner_uuid != scope.owner_uuid or not scope.owner_uuid.int
                    or type(row.line_number) is not int or not 1 <= row.line_number <= 99999
                    or row.line_number in line_numbers or type(row.values) is not tuple
                    or len(row.values) != len(columns)):
                raise ValueError('invalid document line ownership or shape')
            line_numbers.add(row.line_number)
            values = tuple(column.project(value,catalogs) for column,value in zip(columns,row.values))
            ordered.append(BSLDocumentLine(self,row.line_number,values))
        # Order is supplied by an independently verified adapter, never inferred
        # from physical insertion, line-number arithmetic or Python dict order.
        self._rows = tuple(ordered)

    def _column_index(self, name):
        if type(name) is not str:
            raise TypeError('document line column requires String')
        try:
            return self._names.index(name.casefold())
        except ValueError:
            raise ValueError('document line column not found') from None

    def count(self):
        return Decimal(len(self._rows))

    def get_index(self, index):
        if (type(index) is not Decimal or not index.is_finite()
                or index != index.to_integral_value()):
            raise TypeError('document line index requires integer Number')
        if not 0 <= index < len(self._rows):
            raise IndexError('document line index out of bounds')
        return self._rows[int(index)]

    def __iter__(self):
        return iter(self._rows)

    def index_of(self, row):
        if type(row) is not BSLDocumentLine:
            raise TypeError('IndexOf requires a document tabular-section row')
        # EDT IndexOf840: a row not found in this collection returns -1.
        if row._section is not self:
            return Decimal(-1)
        return Decimal(next((i for i,item in enumerate(self._rows) if item is row),-1))

    def find(self, value, column):
        index = self._column_index(column)
        if self._columns[index].kind != 'catalog_ref' or type(value) is not BSLCatalogReference:
            # !todo Scalar collation and multi-column Find require native evidence.
            raise ValueError('only explicit fixed-reference line lookup is prepared')
        return next((row for row in self._rows if row._values[index] == value),None)

    def total(self, column):
        index = self._column_index(column)
        if self._columns[index].kind != 'number':
            # !todo Native conversion/compound-type Total remains unsupported.
            raise ValueError('only explicit numeric line totals are prepared')
        values = tuple(row._values[index] for row in self._rows)
        if not values:
            return Decimal(0)
        if any(not v.is_finite() or len(v.as_tuple().digits)>4096 or abs(v.adjusted())>4096 for v in values):
            raise ValueError('document line total exceeds numeric budget')
        precision = max(v.adjusted() for v in values)-min(v.as_tuple().exponent for v in values)+1+len(str(len(values)))
        if precision > 8192:
            raise ValueError('document line total exceeds numeric budget')
        with localcontext() as context:
            context.prec=max(1,precision)
            context.Emax=999999
            context.Emin=-999999
            return sum(values,Decimal(0))

    def get_method(self, name):
        methods={'count':self.count,'количество':self.count,'get':self.get_index,'получить':self.get_index,
                 'indexof':self.index_of,'индекс':self.index_of,'find':self.find,'найти':self.find,
                 'total':self.total,'итог':self.total}
        method=methods.get(name.casefold())
        return HostFunction(name,method) if method else super().get_method(name)

    def set_index(self, index, value):
        raise ValueError('document tabular sections are read-only')

    def __str__(self):
        raise ValueError('document tabular-section presentation is not admitted')

    # !todo Mutation, Unload, sorting and arbitrary storage/free-chain profiles
    # remain unsupported; no writable object or row is exposed.
