"""Closed configuration layout, not a native window or CurrentPage emulation.

Topology is immutable after admission. Appearance remains each item's own BSL
state; effective appearance is derived without writing into descendants.
"""
MAX_LAYOUT_DEPTH = 8


def validate_layout(rows, items):
    from .form_model import BSLFormGroup, MAX_ITEMS, name
    if type(rows) not in (list, tuple) or not 1 <= len(rows) <= MAX_ITEMS:
        raise ValueError('invalid form layout inventory')
    result = []; seen = {}; depths = {}; page_counts = {}
    for row in rows:
        if type(row) not in (list, tuple) or len(row) != 5:
            raise ValueError('invalid form layout node')
        item_name, parent, kind, orientation, show_title = row
        key = name(item_name).casefold()
        if type(parent) is not str or parent and name(parent) != parent:
            raise ValueError('invalid form layout parent')
        parent_key = parent.casefold()
        item = items.get(key)
        if (item is None or item.name != item_name or key in seen or
                kind not in ('control', 'group', 'pages', 'page') or
                orientation not in ('vertical', 'horizontal') or type(show_title) is not bool):
            raise ValueError('invalid form layout node')
        if (kind != 'control') != (type(item) is BSLFormGroup):
            raise ValueError('layout/control type mismatch')
        if kind in ('control', 'pages') and (orientation != 'vertical' or not show_title):
            raise ValueError('unsupported form layout presentation')
        if parent_key and (parent_key not in seen or seen[parent_key] == 'control'):
            raise ValueError('layout parent must precede child')
        if parent_key and parent != items[parent_key].name:
            raise ValueError('noncanonical form layout parent')
        if (kind == 'page') != (seen.get(parent_key) == 'pages'):
            raise ValueError('pages require direct Page children only')
        depth = depths.get(parent_key, 0) + 1
        if depth > MAX_LAYOUT_DEPTH:
            raise ValueError('form layout depth limit')
        if kind == 'pages': page_counts[key] = 0
        if kind == 'page': page_counts[parent_key] += 1
        seen[key] = kind; depths[key] = depth
        result.append((item_name, parent, kind, orientation, show_title))
    if tuple(row[0] for row in result) != tuple(item.name for item in items.values()):
        raise ValueError('form layout order differs from item order')
    if set(seen) != set(items) or not page_counts and all(row[2] == 'control' for row in result):
        raise ValueError('incomplete form layout')
    if any(count == 0 for count in page_counts.values()):
        raise ValueError('Pages requires at least one Page')
    return tuple(result)


def install_layout(form, rows):
    form._layout = validate_layout(rows, form.items._values)
    form._layout_parents = {row[0].casefold(): row[1].casefold() for row in form._layout}


def effective_state(item):
    visible, enabled, readonly = item.visible, item.enabled, item.read_only
    form = item._form
    parent = form._layout_parents.get(item.name.casefold(), '')
    while parent:
        ancestor = form.items._values[parent]
        visible = visible and ancestor.visible
        enabled = enabled and ancestor.enabled
        readonly = readonly or ancestor.read_only
        parent = form._layout_parents.get(parent, '')
    return visible, enabled, readonly
