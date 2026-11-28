"""Direct canonical stream constructors on scratch files and memory."""
import tempfile
import unittest
from pathlib import Path

from yadinassi import BSLError, Interpreter


class DirectStreamConstructorTests(unittest.TestCase):
    def test_file_stream_and_data_constructor_share_existing_handle(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'run.bin'
            vm.variables['p']=str(path)
            vm.execute('''S=New FileStream(P,FileOpenMode.Create,FileAccess.ReadAndWrite);
W=Новый ЗаписьДанных(S,,ByteOrder.BigEndian); W.WriteInt16(258); W.Close();
S.Seek(0,PositionInStream.Begin); R=New DataReader(S,,ПорядокБайтов.BigEndian);
Out=R.ReadInt16(); R.Close(); S.Close();''')
            self.assertEqual(vm.variables['out'],258)
            self.assertEqual(path.read_bytes(),b'\x01\x02')

    def test_missing_source_does_not_evaluate_later_actuals(self):
        events=[]
        vm=Interpreter(output=events.append)
        self.addCleanup(vm.close)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'not-opened.txt'
            vm.variables['p']=str(path)
            vm.execute('''Function Actual()
    Message("evaluated"); Return P;
EndFunction
R=Новый ЧтениеТекста;''')
            for source in ('W=New DataWriter(,Actual());','R.Open(,Actual());'):
                with self.subTest(source=source), self.assertRaises(BSLError):
                    vm.execute(source)
            self.assertEqual(events,[])
            self.assertFalse(path.exists())
