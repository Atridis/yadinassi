"""Fixture-only owned temporary files; not a new public BSL filesystem API."""
from contextlib import contextmanager
from pathlib import Path
import tempfile


@contextmanager
def temporary_file_helpers(interpreter):
    """The pinned JSON fixture may only allocate/delete its own two files."""
    with tempfile.TemporaryDirectory(prefix='yadinassi-json-native-replay-') as directory:
        root = Path(directory)
        allocated = set()

        def allocate(extension):
            if type(extension) is not str or extension != 'json' or len(allocated) >= 2:
                raise ValueError('json_fixture_path_invalid')
            path = str(root / ('case-' + str(len(allocated)) + '.json'))
            Path(path).touch(exist_ok=False)
            allocated.add(path)
            return path

        def delete(path):
            if type(path) is not str or path not in allocated:
                raise ValueError('json_fixture_path_invalid')
            target = Path(path)
            if target.is_symlink():
                raise ValueError('json_fixture_path_invalid')
            target.unlink(missing_ok=True)

        interpreter.register_function('ПолучитьИмяВременногоФайла', allocate, 'GetTempFileName')
        interpreter.register_function('УдалитьФайлы', delete, 'DeleteFiles', returns_value=False)
        yield allocated


def execution_script(base):
    marker = 'interpreter.execute(source_text, str(source))'
    if base.count(marker) != 1:
        raise ValueError('json_fixture_script_invalid')
    replacement = '''
helper_path = Path(sys.argv[1]) / "scripts/native_1c_json_family_replay.py"
helper_spec = importlib.util.spec_from_file_location("json_fixture_replay", helper_path)
helper = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(helper)
with helper.temporary_file_helpers(interpreter):
    interpreter.execute(source_text, str(source))
'''
    return base.replace(marker, replacement)
