"""Ordered iterative regex VM, bounded even when backtracking is exponential.

No host regular-expression engine, recursion during matching, or timeout claim.
Unicode matching/flags are provisional until the source-bound native batch.
"""
from . import regex_parser as limits
from .strings import _simple_lower, _simple_upper


class Program:
    def __init__(self, node, groups, budget):
        self.code = []
        self.groups = groups
        self.flags = {}
        self.loops = 0
        self.budget = budget
        end = self.emit(('match',))
        end = self.emit(('save', 1, end))
        self.start = self.emit(('save', 0, self.compile(node, end)))

    def emit(self, instruction):
        self.budget.tick()
        if len(self.code) >= limits.MAX_CODE:
            raise limits.RegexLimitError('Регулярное выражение: слишком большой шаблон')
        self.code.append(instruction)
        return len(self.code) - 1

    def compile(self, node, after, flags=(0, 0)):
        self.budget.tick()
        kind = node[0]
        if kind == 'flags':
            enabled = (flags[0] | node[1]) & ~node[2]
            disabled = (flags[1] | node[2]) & ~node[1]
            return self.compile(node[3], after, (enabled, disabled))
        if kind == 'look':
            end = self.emit(('look_match',))
            start = self.compile(node[2], end, flags)
            return self.emit(('look', node[1], start, after))
        if kind == 'seq':
            for child in reversed(node[1]): after = self.compile(child, after, flags)
            return after
        if kind == 'alt':
            starts = [self.compile(child, after, flags) for child in node[1]]
            start = starts[-1]
            for other in reversed(starts[:-1]): start = self.emit(('split', other, start))
            return start
        if kind == 'group':
            end = self.emit(('save', node[1] * 2 + 1, after))
            return self.emit(('save', node[1] * 2, self.compile(node[2], end, flags)))
        if kind == 'repeat':
            _, child, lower, upper, lazy = node
            if upper is None:
                if self.loops >= limits.MAX_LOOPS:
                    raise limits.RegexLimitError('Регулярное выражение: слишком много циклов')
                loop = self.loops; self.loops += 1
                split = self.emit(('pending',))
                progress = self.emit(('progress', loop, split, after))
                body = self.compile(child, progress, flags)
                self.code[split] = ('split', after, body) if lazy else ('split', body, after)
                after = self.emit(('mark', loop, split))
            else:
                for _ in range(upper - lower):
                    start = self.compile(child, after, flags)
                    after = self.emit(('split', after, start) if lazy else ('split', start, after))
            for _ in range(lower): after = self.compile(child, after, flags)
            return after
        pc = self.emit((kind, *node[1:], after))
        self.flags[pc] = flags
        return pc


def _word(c):
    # !todo Native calibration must settle Unicode categories and combining marks.
    return bool(c) and (c == '_' or c.isalnum())


def _category(kind, c):
    if kind.lower() == 'd': match = c.isdecimal()
    elif kind.lower() == 's': match = c in ' \t\n\r\f\v' or c.isspace()
    else: match = _word(c)
    return not match if kind.isupper() else match


def _equal(a, b, ignore):
    return a == b or (ignore and (_simple_lower(a) == _simple_lower(b)
                                 or _simple_upper(a) == _simple_upper(b)))


def _class(parts, c, ignore, budget):
    for part in parts:
        budget.tick()
        if part[0] == 'char': match = _equal(c, part[1], ignore)
        elif part[0] == 'category': match = _category(part[1], c)
        else:
            match = part[1] <= c <= part[2]
            if ignore:
                match = match or _simple_lower(part[1]) <= _simple_lower(c) <= _simple_lower(part[2])
                match = match or _simple_upper(part[1]) <= _simple_upper(c) <= _simple_upper(part[2])
        if match: return True
    return False


def _assertion(kind, text, pos, multiline):
    if kind == '^': return pos == 0 or (multiline and text[pos - 1:pos] == '\n')
    if kind == '$': return pos == len(text) or (multiline and text[pos:pos + 1] == '\n')
    boundary = _word(text[pos - 1] if pos else '') != _word(text[pos] if pos < len(text) else '')
    return boundary if kind == 'b' else not boundary


def run(program, text, start, budget, ignore=False, multiline=False, full=False):
    """One iterative search with isolated atomic assertion frames and one budget."""
    slots = (program.groups + 1) * 2
    budget.tick(slots + program.loops)
    pending = [(program.start, start, (None,) * slots, (None,) * program.loops)]
    frames = []
    base_flags = (1 if ignore else 0) | (2 if multiline else 0)

    def push(state):
        budget.tick(len(frames) + 1)
        if len(pending) + sum(len(f[0]) for f in frames) + len(frames) >= limits.MAX_STATES:
            raise limits.RegexLimitError('Регулярное выражение: превышен предел состояний')
        pending.append(state)

    while pending or frames:
        budget.tick()
        if not pending:
            # A failed positive assertion fails its caller path; a failed negative
            # assertion succeeds with the original captures and input position.
            pending, positive, after, origin, captures, marks = frames.pop()
            if not positive: push((after, origin, captures, marks))
            continue
        pc, pos, captures, marks = pending.pop()
        while True:
            budget.tick()
            instruction = program.code[pc]; kind = instruction[0]
            if kind == 'match':
                if frames: raise ValueError('Регулярное выражение: неверный стек утверждений')
                if not full or pos == len(text): return captures
                break
            if kind == 'look_match':
                if not frames: raise ValueError('Регулярное выражение: неверное утверждение')
                # Discard all alternatives inside the assertion: lookahead is atomic.
                outer, positive, after, origin, original, original_marks = frames.pop()
                pending = outer
                if positive: push((after, origin, captures, original_marks))
                break
            if kind == 'look':
                if len(frames) >= limits.MAX_DEPTH:
                    raise limits.RegexLimitError('Регулярное выражение: глубина утверждений')
                frames.append((pending, instruction[1], instruction[3], pos, captures, marks))
                pending = []
                push((instruction[2], pos, captures, marks))
                break
            if kind == 'split':
                push((instruction[2], pos, captures, marks)); pc = instruction[1]
                continue
            if kind == 'save':
                budget.tick(slots)
                values = list(captures); values[instruction[1]] = pos
                captures = tuple(values); pc = instruction[2]; continue
            if kind == 'mark' or kind == 'progress':
                if kind == 'progress' and marks[instruction[1]] == pos:
                    pc = instruction[3]; continue
                budget.tick(program.loops)
                values = list(marks); values[instruction[1]] = pos
                marks = tuple(values); pc = instruction[2]; continue
            enabled, disabled = program.flags.get(pc, (0, 0))
            flags = (base_flags | enabled) & ~disabled
            ignore_case = bool(flags & 1)
            if kind == 'assert':
                if not _assertion(instruction[1], text, pos, bool(flags & 2)): break
                pc = instruction[-1]; continue
            if kind == 'backref':
                left, right = captures[instruction[1]*2:instruction[1]*2+2]
                if left is None or right is None: break
                length = right - left
                budget.tick(length)
                if pos + length > len(text): break
                matched = all(_equal(text[left+i], text[pos+i], ignore_case) for i in range(length))
                if not matched: break
                pos += length; pc = instruction[-1]; continue
            if pos >= len(text): break
            c = text[pos]
            if kind == 'char': matched = _equal(c, instruction[1], ignore_case)
            elif kind == 'dot': matched = bool(flags & 4) or c != '\n'
            elif kind == 'category': matched = _category(instruction[1], c)
            elif kind == 'class': matched = _class(instruction[2], c, ignore_case, budget) != instruction[1]
            else: raise ValueError('Регулярное выражение: неверная инструкция')
            if not matched: break
            pos += 1; pc = instruction[-1]
    return None
