"""Closed immutable identities for the three independently bounded tree shards."""
from typing import NamedTuple


class Profile(NamedTuple):
    name: str
    schema: str
    stage_schema: str
    case: str
    source_sha256: str
    count: int
    contract: str
    calibration_marker: str
    print_sites: int
    artifact: str

    @property
    def source(self):
        return 'integrational_tests/measurements/' + self.case + '.bsl'

    @property
    def target(self):
        return 'scenarios/' + self.case + '.bsl'


FILL = Profile('tree-v1', 'native-1c-tree-v1', 'native-1c-tree-stage-v1',
    'tree_fill_values', '58d466f3a9a181891fd97e205d115f0ce32b620f8fa8df3d56f4516405a65c90',
    34, 'native_1c_tree_fill_contract', '\nCalibration = TreeFillCalibrate();\n', 3, 'tree')
COPY = Profile('tree-copy-v1', 'native-1c-tree-copy-v1', 'native-1c-tree-copy-stage-v1',
    'tree_copy', 'aadb8667848308bc4e14b82764dd693bc30fdd6a184598caf479e5a0cdc32572',
    11, 'native_1c_tree_copy_contract', '\nСообщить("TC-P: [" + TCRepeatedAccessProbe() + "]");\n', 3, 'tree-copy')

SORT = Profile('tree-sort-v1', 'native-1c-tree-sort-v1', 'native-1c-tree-sort-stage-v1',
    'tree_sort', '5607a0c42901d624cfae1d166aed8d3ea258a2b0c8e0c894dcd032526a6fb5a3',
    22, 'native_1c_tree_sort_contract', '\nСообщить("TS-C1: [" + TSCalibrate() + "]");\n', 2, 'tree-sort')


def select(name='tree-v1'):
    if type(name) is not str:
        raise ValueError('invalid_tree_profile')
    if name == FILL.name:
        return FILL
    if name == COPY.name:
        return COPY
    if name == SORT.name:
        return SORT
    raise ValueError('invalid_tree_profile')
