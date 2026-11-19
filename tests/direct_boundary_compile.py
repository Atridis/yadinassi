"""Compile boundary fixtures with the production owning compiler, not an oracle.

No repair switches or test executor: callers supply the real context and state.
"""
from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
from yadinassi.syntax.parser import parse


def compile_boundary(source, *, source_name="boundary.bsl", constructors=(), module_names=()):
    return compile_owned(parse(source, source_name), source_text=source,
                         source_name=source_name, constructors=constructors,
                         module_names=module_names, authority_checks=True)
