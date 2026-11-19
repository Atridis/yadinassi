"""Immutable invocation syntax, prepared independently of live call authority."""
from dataclasses import dataclass
from yadinassi.types.errors import BSLError
from yadinassi.syntax.parser import validate_labels


@dataclass(frozen=True)
class ParameterLayout:
    name: str
    by_value: bool
    default: object


@dataclass(frozen=True)
class RoutineLayout:
    parameters: tuple
    required: int
    defaults: tuple
    byref_indexes: tuple
    label_error: object
    slots: int


def layout_slots(routine):
    # Fixed reservation includes descriptor fields, sequence entries, optional
    # defaults/byref positions and diagnostic scalars. Shared parameter lists
    # do not make per-routine layouts free. Check before allocating the layout.
    return 8 + 6 * len(routine.parameters)


def prepare_layout(routine):
    parameters = tuple(ParameterLayout(p.name.casefold(), p.by_value, p.default)
                       for p in routine.parameters)
    required = max((i + 1 for i, p in enumerate(parameters) if p.default is None), default=0)
    label_error = None
    try:
        validate_labels(routine.body)
    except BSLError as error:
        # Preserve call-time error precedence for directly supplied routines.
        # Never retain an exception/traceback or precomputed permission.
        label_error = (error.message, error.source, error.line, error.column)
    return RoutineLayout(parameters, required,
                         tuple(p.default for p in parameters if p.default is not None),
                         tuple(i for i, p in enumerate(parameters) if not p.by_value),
                         label_error, layout_slots(routine))
