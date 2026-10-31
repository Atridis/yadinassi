"""Closed immutable identities for the independently bounded scalar and tree shards."""
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


COLUMNS_MOVE = Profile('tree-columns-move-v1', 'native-1c-tree-columns-move-v1', 'native-1c-tree-columns-move-stage-v1',
    'tree_columns_move', 'af85ce64db72688c4520912756cda36eb95355af88d8f2c56d4ffbb662879b22',
    29, 'native_1c_tree_columns_move_contract', '\nСообщить("CM-C1: [" + CMCalibrate() + "]");\n', 2, 'tree-columns-move')


COLUMNS_MOVE_BOUNDARY = Profile('tree-columns-move-boundary-v1', 'native-1c-tree-columns-move-boundary-v1', 'native-1c-tree-columns-move-boundary-stage-v1',
    'tree_columns_move_boundary', 'd35743dc427a908906d225c538b68e621dd9f5e0f830a434de662f1508d14e11',
    18, 'native_1c_tree_columns_move_boundary_contract', '\nСообщить("CB-C1: [" + CBCalibrate() + "]");\n', 2, 'tree-columns-move-boundary')


COLUMNS_MOVE_TAIL = Profile('tree-columns-move-tail-v1', 'native-1c-tree-columns-move-tail-v1', 'native-1c-tree-columns-move-tail-stage-v1',
    'tree_columns_move_tail', 'db973872a07d3026d4a809a0b03e6a722687ace845a182166013c26d1d201fa1',
    7, 'native_1c_tree_columns_move_tail_contract', '\nСообщить("CT-C1: [" + CTCalibrate() + "]");\n', 2, 'tree-columns-move-tail')


COLUMNS_CLEAR = Profile('tree-columns-clear-v1', 'native-1c-tree-columns-clear-v1', 'native-1c-tree-columns-clear-stage-v1',
    'tree_columns_clear', 'c3ebd1aa58bb2f6bc7570108a0e6c2f30207cb316cfb750ae383591c7bdf8615',
    13, 'native_1c_tree_columns_clear_contract', '\nСообщить("CC-C1: [" + CCCalibrate() + "]");\n', 2, 'tree-columns-clear')



COLUMNS_CLEAR_LIFETIME = Profile('tree-columns-clear-lifetime-v1', 'native-1c-tree-columns-clear-lifetime-v1', 'native-1c-tree-columns-clear-lifetime-stage-v1',
    'tree_columns_clear_lifetime', '5cb69498147e03354f140d571f921adfa7cf940deab3179d1cb20f4c444ea352',
    7, 'native_1c_tree_columns_clear_lifetime_contract', '\nСообщить("CL-C1: [" + CLCalibrate() + "]");\n', 2, 'tree-columns-clear-lifetime')


COLUMNS_CLEAR_METADATA = Profile('tree-columns-clear-metadata-v1', 'native-1c-tree-columns-clear-metadata-v1', 'native-1c-tree-columns-clear-metadata-stage-v1',
    'tree_columns_clear_metadata', 'c120b7813f7035c44bb98aac76dad4bf435417eab1ef0ad732c3e7ef7a02e435',
    4, 'native_1c_tree_columns_clear_metadata_contract', '\nСообщить("CD-C1: [" + CCCalibrate() + "]");\n', 2, 'tree-columns-clear-metadata')


COLUMNS_DELETE = Profile('tree-columns-delete-v1', 'native-1c-tree-columns-delete-v1', 'native-1c-tree-columns-delete-stage-v1',
    'tree_columns_delete', '250c6a8026b3a88c803de7e06565f6c50add4c67cd91a65ffe6c2fceb0d77f2d',
    15, 'native_1c_tree_columns_delete_contract', '\nСообщить("DL-C1: [" + CCCalibrate() + "]");\n', 2, 'tree-columns-delete')

COLUMNS_DELETE_STRING = Profile('tree-columns-delete-string-v1', 'native-1c-tree-columns-delete-string-v1', 'native-1c-tree-columns-delete-string-stage-v1',
    'tree_columns_delete_string', 'ebb9728d4f4e42fbabbc8975be160989f669540cfbfc200994570e3aeb1beaaf',
    7, 'native_1c_tree_columns_delete_string_contract', '\nСообщить("DS-C1: [" + CCCalibrate() + "]");\n', 2, 'tree-columns-delete-string')

FORMAT_NUMBERS = Profile('format-numbers-v1', 'native-1c-format-numbers-v1', 'native-1c-format-numbers-stage-v1',
    'format_numbers', 'a7f8e3c6105d4a7f28ef08a0865abcf01f7465f236fffe189c2da7272df04d84',
    50, 'native_1c_format_numbers_contract', '\nСообщить("FM-C1: [" + FMEncode("") + "]");\n', 5, 'format-numbers')

FORMAT_DATES = Profile('format-dates-v1', 'native-1c-format-dates-v1', 'native-1c-format-dates-stage-v1',
    'format_dates', '7290d1cd2cb6b9f3c77679d8e62a920b87c91417a8569502afe314abb09fa4fb',
    58, 'native_1c_format_dates_contract', '\nСообщить("FD-C1: [" + FDEncode("") + "]");\n', 5, 'format-dates')

def select(name='tree-v1'):
    if type(name) is not str:
        raise ValueError('invalid_tree_profile')
    if name == FILL.name:
        return FILL
    if name == COPY.name:
        return COPY
    if name == SORT.name:
        return SORT
    if name == COLUMNS_MOVE.name:
        return COLUMNS_MOVE
    if name == COLUMNS_MOVE_BOUNDARY.name:
        return COLUMNS_MOVE_BOUNDARY
    if name == COLUMNS_MOVE_TAIL.name:
        return COLUMNS_MOVE_TAIL
    if name == COLUMNS_CLEAR.name:
        return COLUMNS_CLEAR
    if name == COLUMNS_CLEAR_LIFETIME.name:
        return COLUMNS_CLEAR_LIFETIME
    if name == COLUMNS_CLEAR_METADATA.name:
        return COLUMNS_CLEAR_METADATA
    if name == COLUMNS_DELETE.name:
        return COLUMNS_DELETE
    if name == COLUMNS_DELETE_STRING.name:
        return COLUMNS_DELETE_STRING
    if name == FORMAT_DATES.name:
        return FORMAT_DATES
    if name == FORMAT_NUMBERS.name:
        return FORMAT_NUMBERS
    raise ValueError('invalid_tree_profile')
