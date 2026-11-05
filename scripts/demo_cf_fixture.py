"""Materialize the exact reviewed demo fixture. Never imports or executes its code."""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import stat
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'demo_cf'
ARCHIVE_SHA256 = 'a2ee9c12d9a91000b282ce3ed5c9ec3936e38bdcb4d57ac4ee11871aa9c6799f'
ARCHIVE_SIZE = 33250


def fixture_files(archive=None):
    """Return normalized XML/BSL bytes after checking the entire pinned archive."""
    archive = ROOT / 'original.zip' if archive is None else Path(archive)
    with archive.open('rb') as stream:
        raw = stream.read(ARCHIVE_SIZE + 1)
    if len(raw) != ARCHIVE_SIZE or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('demo archive identity mismatch')
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    expected = manifest['entries']
    if (manifest['schema'] != 1 or manifest['archive_sha256'] != ARCHIVE_SHA256
            or manifest['archive_size'] != ARCHIVE_SIZE or len(expected) != 40):
        raise ValueError('demo manifest identity mismatch')
    result = {}
    seen = set()
    total = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        entries = source.infolist()
        if len(entries) != len(expected):
            raise ValueError('demo inventory mismatch')
        for item, witness in zip(entries, expected):
            mode = item.external_attr >> 16
            if (item.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or item.file_size > 65536 or item.compress_size > 65536):
                raise ValueError('unsupported demo entry')
            decoded = item.filename if item.flag_bits & 0x800 else item.filename.encode('cp437').decode('utf-8')
            normalized = unicodedata.normalize('NFC', decoded)
            parts = normalized.rstrip('/').split('/')
            if ('\\' in normalized or '\x00' in normalized or any(p in ('', '.', '..') for p in parts)
                    or parts[0] != 'demo_cf' or normalized in seen):
                raise ValueError('unsafe demo path')
            seen.add(normalized)
            relative = normalized.removeprefix('demo_cf/')
            data = source.read(item)  # ZIP CRC is checked; source is already hash-bound.
            total += len(data)
            copied = not item.is_dir() and PurePosixPath(relative).suffix in ('.xml', '.bsl')
            actual = dict(zip_name_decoded=decoded, staged_name=relative,
                          size=len(data), sha256=hashlib.sha256(data).hexdigest(), copied=copied)
            if actual != witness or total > 1048576:
                raise ValueError('demo entry identity mismatch')
            if copied:
                result[relative] = data
    if (len(result) != 19 or sum(p.endswith('.xml') for p in result) != 15
            or sum(p.endswith('.bsl') for p in result) != 4):
        raise ValueError('demo source inventory mismatch')
    return result


def stage(destination):
    """Write into a new directory under a caller-owned parent; never overwrite.

    The caller must keep the parent private from concurrent hostile mutation.
    This is an exact-fixture helper, not a general archive extraction API.
    On I/O failure an incomplete directory may remain and must not be used.
    """
    files = fixture_files()
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    for relative, data in files.items():
        path = destination.joinpath(*PurePosixPath(relative).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    return destination


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='new directory inside an owned existing parent')
    args = parser.parse_args()
    stage(args.destination)
    print('Staged 15 XML and 4 BSL files. No demo code or native 1C was executed.')
