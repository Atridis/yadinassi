"""Invented bounded failure logs; never native compiler evidence."""
from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import catalog_read_diagnostics as subject
import catalog_read_fixture as fixture
import catalog_read_instrument as instrument
from snapshots import OracleError


class CatalogReadDiagnosticsTests(unittest.TestCase):
    def test_one_readonly_compile_and_finite_projection(self):
        class Backend:
            counter=9
            def __init__(self,path):self.evidence=path;self.calls=[]
            def quiescent(self):return True
            def remaining(self):return 1
            def budgets(self):pass
            def command(self,*args):self.calls.append(args);return ['fixed']
            def process(self,args,label):
                self.calls.append((args,label))
                Path(args[args.index('/Out')+1]).write_text('{ОбщийМодуль.NativeOracleServer.Модуль(123,4)}: Переменная не определена (PRIVATE)\n{PrivateModule(9,1)}: PRIVATE')
                Path(args[args.index('/DumpResult')+1]).write_text('1')
                raise OracleError('process_failed')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'control.json').write_text('private');(p/'completion.json').write_text('private')
            backend=Backend(p);v=subject.collect(backend,p,None)
            self.assertEqual(len(backend.calls),2)
            args=backend.calls[1][0]
            self.assertIn('/CheckConfig',args);self.assertNotIn('/UpdateDBCfg',args)
            self.assertEqual(v['markers'],{'control':'nonempty','result':'absent','completion':'nonempty','completion.pending':'absent'})
            self.assertEqual(v['compile']['issues'][0],dict(module='server',line=123,column=4,category='undefined_symbol'))
            self.assertEqual(v['compile']['issues'][1],dict(module='other',line=0,column=0,category='other'))
            self.assertNotIn('PRIVATE',repr(v));self.assertNotIn('PrivateModule',repr(v))
            subject.validate(v)
    def test_nonquiescent_never_starts_diagnostic_process(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            b=Mock(evidence=Path(tmp));b.quiescent.return_value=False
            value=subject.collect(b,Path(tmp),None)
            b.process.assert_not_called();self.assertEqual(value['compile']['state'],'unavailable')
    def test_marker_read_rejects_indirect_and_oversized_without_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);target=p/'file';target.write_bytes(b'x'*65)
            self.assertEqual(subject.read(target,64),('unavailable',None))
            link=p/'link'
            try:link.symlink_to(target)
            except OSError:self.skipTest('symlink unavailable')
            self.assertEqual(subject.read(link,100),('unavailable',None))
    def test_setup_declarations_are_module_scope_before_bodies(self):
        _,_,files=fixture.load(1)
        for i,state in enumerate(fixture.STATES):
            text=instrument.wrap(files['setup-'+state+'.bsl'],'S'+str(i))
            self.assertLess(text.index(f'Функция S{i}CRCount('),text.index(f'Функция S{i}CRRun()'))
            self.assertNotRegex(text,r'(?m)^\s*Выполнить\(')
            body=text.split(f'Функция S{i}CRRun()',1)[1]
            self.assertNotIn('Функция ',body)

if __name__=='__main__':unittest.main()
