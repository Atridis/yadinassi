"""Small bare Structure operations, not a legacy/host adaptation layer.

Fill copies existing target/source keys only and shares values, including None.
Filters are comma-separated canonicalized name sets. Unknown names are skipped;
exclusions win. None means no filter; empty include means copy nothing. This is
not the platform-specific legacy partial-write/error-order contract.
"""
from .native_bare_collections import BareStructure


def _filter_names(spec):
    if type(spec) is not str:
        raise TypeError('Bare FillPropertyValues filters must be strings or None')
    names = (part.strip().casefold() for part in spec.split(','))
    return {name for name in names if name}


def bare_fill_property_values(target, source, include=None, exclude=None):
    """Fill two exact bare structures; no getattr/setattr, coercion or fallback."""
    if type(target) is not BareStructure or type(source) is not BareStructure:
        raise NotImplementedError('Bare FillPropertyValues requires two BareStructure values')
    if include is None and exclude is None:
        # The common two-argument route parses/allocates no filter structures.
        for key in dict.keys(target):
            if key in source:
                target[key] = source[key]
        return
    selected = None if include is None else _filter_names(include)
    excluded = set() if exclude is None else _filter_names(exclude)
    for key in dict.keys(target):
        if key in source and (selected is None or key in selected) and key not in excluded:
            target[key] = source[key]
