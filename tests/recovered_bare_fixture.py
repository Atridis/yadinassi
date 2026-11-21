"""Test-only explicit caller of reconstructed compiler; no production routing."""
from yadinassi import Interpreter as PublicInterpreter
from yadinassi.execution.codegen import native_bare_compiler as bare
from yadinassi.syntax.parser import parse

class Interpreter(PublicInterpreter):
    def execute(self,text,source='<recovered test>'):
        if self.execution_backend != 'python-direct':
            return super().execute(text,source)
        return bare.execute(self,parse(text,source,compilation_profile=self.compilation_profile),source_text=text,source_name=source)
    def execute_program(self,program):
        if self.execution_backend != 'python-direct':return super().execute_program(program)
        return bare.execute(self,program)
    def prepare(self,text,source='<recovered test>'):
        return bare.prepare_module(self,parse(text,source,compilation_profile=self.compilation_profile),source_text=text,source_name=source)
    def prepare_program(self,program):return bare.prepare_module(self,program)
    def execute_prepared(self,plan):return bare.execute_prepared(self,plan)
