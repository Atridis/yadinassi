"""Small correctness checks for the opt-in benchmark; no timing assertions."""
import importlib.util
from pathlib import Path
import unittest
from decimal import Decimal
from yadinassi import Interpreter

PATH=Path(__file__).resolve().parents[1]/'benchmarks'/'for_loop.py'
spec=importlib.util.spec_from_file_location('for_benchmark',PATH)
benchmark=importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class ForBenchmarkContractTests(unittest.TestCase):
    def test_every_fixture_runs_in_both_scopes(self):
        for scope in ('module','routine'):
            for case in benchmark.BODIES:
                with self.subTest(scope=scope,case=case):
                    vm=Interpreter();self.addCleanup(vm.close)
                    vm.execute(benchmark.fixture(case,scope,11))
                    self.assertEqual(vm.variables['результат'],Decimal(benchmark.expected(case,11)))

    def test_user_ten_million_arithmetic_expected(self):
        self.assertEqual(benchmark.expected('arithmetic',10000000),149999945000000)

if __name__=='__main__':unittest.main()
