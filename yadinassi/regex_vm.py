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

    def compile(self, node, after):
        self.budget.tick()
        kind = node[0]
        if kind == 'seq':
            for child in reversed(node[1]): after = self.compile(child, after)
            return after
        if kind == 'alt':
            starts = [self.compile(child, after) for child in node[1]]
            start = starts[-1]
            for other in reversed(starts[:-1]): start = self.emit(('split', other, start))
            return start
        if kind == 'group':
            end = self.emit(('save', node[1] * 2 + 1, after))
            return self.emit(('save', node[1] * 2, self.compile(node[2], end)))
        if kind == 'repeat':
            _, child, lower, upper, lazy = node
            if upper is None:
                if self.loops >= limits.MAX_LOOPS:
                    raise limits.RegexLimitError('Регулярное выражение: слишком много циклов')
                loop = self.loops; self.loops += 1
                split = self.emit(('pending',))
                progress = self.emit(('progress', loop, split, after))
                body = self.compile(child, progress)
                self.code[split] = ('split', after, body) if lazy else ('split', body, after)
                after = self.emit(('mark', loop, split))
            else:
                for _ in range(upper - lower):
                    start = self.compile(child, after)
                    after = self.emit(('split', after, start) if lazy else ('split', start, after))
            for _ in range(lower): after = self.compile(child, after)
            return after
        return self.emit((kind, *node[1:], after))


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
    slots = (program.groups + 1) * 2
    budget.tick(slots + program.loops)
    pending = [(program.start, start, (None,) * slots, (None,) * program.loops)]
    while pending:
        budget.tick()
        pc, pos, captures, marks = pending.pop()
        while True:
            budget.tick()
            instruction = program.code[pc]; kind = instruction[0]
            if kind == 'match':
                if not full or pos == len(text): return captures
                break
            if kind == 'split':
                if len(pending) >= limits.MAX_STATES:
                    raise limits.RegexLimitError('Регулярное выражение: превышен предел состояний')
                pending.append((instruction[2], pos, captures, marks)); pc = instruction[1]
                continue
            if kind == 'save':
                budget.tick(slots)
                values = list(captures); values[instruction[1]] = pos
                captures = tuple(values); pc = instruction[2]; continue
            if kind == 'mark' or kind == 'progress':
                if kind == 'progress' and marks[instruction[1]] == pos:
                    # A nullable repeated body may match once, but never spin.
                    pc = instruction[3]; continue
                budget.tick(program.loops)
                values = list(marks); values[instruction[1]] = pos
                marks = tuple(values); pc = instruction[2]; continue
            if kind == 'assert':
                if not _assertion(instruction[1], text, pos, multiline): break
                pc = instruction[-1]; continue
            if pos >= len(text): break
            c = text[pos]
            if kind == 'char': matched = _equal(c, instruction[1], ignore)
            elif kind == 'dot': matched = c != '\n'
            elif kind == 'category': matched = _category(instruction[1], c)
            elif kind == 'class':
                matched = _class(instruction[2], c, ignore, budget) != instruction[1]
            else: raise ValueError('Регулярное выражение: неверная инструкция')
            if not matched: break
            pos += 1; pc = instruction[-1]
    return None
