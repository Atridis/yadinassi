"""Closed immutable identities for the two independently bounded tree shards."""
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
    'tree_copy', 'e097e2e51bbe4865297083e4a522f2ad6a5b683288255a0395428d6134fbaf05',
    10, 'native_1c_tree_copy_contract', '\nСообщить("TC-C: [" + TCCalibrate() + "]");\n', 2, 'tree-copy')


def select(name='tree-v1'):
    if type(name) is not str:
        raise ValueError('invalid_tree_profile')
    if name == FILL.name:
        return FILL
    if name == COPY.name:
        return COPY
    raise ValueError('invalid_tree_profile')
