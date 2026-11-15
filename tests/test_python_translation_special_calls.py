import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.compiled_backend import Engine

class SpecialCalls(unittest.TestCase):
    def run_source(self,source,setup=lambda vm:None):
        outcomes=[]
        for backend in ('interpreter','compiled-strict'):
            vm=Interpreter(execution_backend=backend,compiled_plain_routines=True)
            setup(vm)
            with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
                for part in source.split('//TEST_BODY'):
                    vm.execute(part,'translated-special.bsl')
            outcomes.append(vm.variables.get('r'))
            if backend=='compiled-strict':
                stats=vm.compiled_backend_stats
                self.assertEqual(stats['interpreter_fallbacks'],0)
                self.assertEqual(stats['inline_fragments'],0)
                self.assertEqual(stats.get('plain_adapter_blocks',0),0)
                self.assertFalse(stats.get('force_translation_gaps',{}))
            self.assertIsNone(vm.locals);self.assertEqual(vm._eval_depth[0],0)
            vm.close()
        self.assertEqual(*outcomes)
        return outcomes[0]

    def test_eval_live_names_and_nested(self):
        self.assertEqual(self.run_source('x=3;r=Eval("x+Eval(""2"")");'),5)

    def test_eval_whole_expression_parsed_before_effect(self):
        for backend in ('interpreter','compiled-strict'):
            vm=Interpreter(execution_backend=backend);events=[]
            vm.register_function('Tick',lambda:events.append(1))
            with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
                with self.assertRaises(BSLError):vm.execute('r=Eval("Tick()+");')
            self.assertEqual(events,[]);self.assertEqual(vm._eval_depth[0],0)

    def test_json_roundtrip(self):
        self.assertEqual(self.run_source('w=New JSONWriter;w.SetString();WriteJSON(w,New Structure("n",7));s=w.Close();reader=New JSONReader;reader.SetString(s);v=ReadJSON(reader);reader.Close();r=v.n;'),7)

    def test_json_conversion_callback(self):
        source='''Function Convert(Name,Value,Extra,Cancel) Export
            Return Extra;
        EndFunction
        //TEST_BODY
        w=New JSONWriter;w.SetString();WriteJSON(w,New Structure("n",New UUID("12345678-1234-1234-1234-123456789abc")),,"Convert",ThisObject,2);s=w.Close();
        reader=New JSONReader;reader.SetString(s);v=ReadJSON(reader);reader.Close();r=v.n;'''
        self.assertEqual(self.run_source(source),2)

    def test_callback_procedure_and_result(self):
        source='''Var Result;
        Procedure Record(Value,Extra) Export Result=Value+Extra;EndProcedure
        //TEST_BODY
        c=New CallbackDescription("Record",ThisObject,4);RunCallback(c,3);r=Result;'''
        self.assertEqual(self.run_source(source),7)

    def test_callback_invalid_arity_before_argument_effect(self):
        for backend in ('interpreter','compiled-strict'):
            events=[];vm=Interpreter(execution_backend=backend);vm.register_function('Tick',lambda:events.append(1))
            with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
                with self.assertRaises(BSLError):vm.execute('RunCallback(Tick(),Tick(),Tick());')
            self.assertEqual(events,[])
