"""Prepared syntax facts do not replace live import/namespace authorization."""
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.errors import BSLError
from yadinassi.experimental_naked_boundaries import BoundaryViolation

class PreparedImportFactsTests(unittest.TestCase):
    def test_unrelated_top_level_statements_do_not_add_preflight_entries(self):
        counts=[]
        for n in (0,1024):
            vm=Interpreter();plan=vm.prepare('If False Then X=1;EndIf;'*n+'R=1;')
            vm.execute_prepared(plan);entries=[]
            def profile(frame,event,arg):
                if event=='call' and frame.f_code.co_filename.endswith('python_direct_imports.py'):
                    entries.append(frame.f_code.co_name)
            sys.setprofile(profile)
            try:vm.execute_prepared(plan)
            finally:sys.setprofile(None)
            self.assertEqual(vm.variables['r'],1);counts.append(entries);vm.close()
        self.assertEqual(counts[0],counts[1])

    def test_facts_are_immutable_and_caller_ast_does_not_change_them(self):
        vm=Interpreter();program=parse('Var X Export;X=3;');plan=vm.prepare_program(program)
        program[0].names.append('Changed')
        facts=plan._import_facts
        with self.assertRaises(FrozenInstanceError):facts.source='changed'
        self.assertEqual(facts.variable_exports,frozenset({'x'}))
        vm.execute_prepared(plan);self.assertEqual(vm.variables['x'],3)
        self.assertNotIn('changed',vm.variables);vm.close()

    def test_live_import_collision_and_loader_override_rejected_before_effects(self):
        for mutation in ('collision','loader'):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'Side.bsl').write_text('Var N Export;N=3;',encoding='utf-8')
                vm=Interpreter();effects=[];vm.register_function('Effect',lambda:effects.append(1))
                plan=vm.prepare_program(parse('// #Import Side.bsl\nEffect();',str(root/'Main.bsl')))
                if mutation=='collision':vm.variables['side']=1
                else:vm._check_import_binding=lambda *args:None
                with self.assertRaises(BSLError if mutation=='collision' else BoundaryViolation):vm.execute_prepared(plan)
                self.assertEqual(effects,[]);self.assertEqual(vm.imports,{})
                vm.close()

    def test_forged_namespace_after_success_is_not_authorized_by_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'Side.bsl').write_text('Var N Export;N=3;',encoding='utf-8')
            vm=Interpreter();effects=[];vm.register_function('Effect',lambda:effects.append(1))
            plan=vm.prepare_program(parse('// #Import Side.bsl\nEffect();R=Side.N;',str(root/'Main.bsl')))
            vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],3)
            effects.clear();vm.imports['side']=object()
            with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
            self.assertEqual(effects,[]);vm.close()
