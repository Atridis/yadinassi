"""Bounded host-directory reader for official XML/BSL configuration packages."""
import os
import stat
import sys
from pathlib import Path
from .configuration_xml import import_configuration, MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES


def _snapshot(info):
    """Compare timestamps only between observations from the same stat API."""
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            getattr(info, 'st_birthtime_ns', None),
            getattr(info, 'st_file_attributes', 0))


def _path_matches_descriptor(path_info, descriptor_info):
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if identity(path_info) != identity(descriptor_info):
        return False
    if sys.platform != 'win32':
        return path_info.st_ctime_ns == descriptor_info.st_ctime_ns
    # CPython 3.12 Windows stat(path) exposes creation time as ctime,
    # while fstat(fd) exposes change time (CPython issue #157671).
    # Keep full ctime comparisons within each API before/after the read.
    births = (getattr(path_info, 'st_birthtime_ns', None),
              getattr(descriptor_info, 'st_birthtime_ns', None))
    if births != (None, None):
        return all(type(value) is int for value in births) and births[0] == births[1]
    return True  # Older Windows Python: no portable cross-API creation field.


def _host_directory(directory):
    """Static no-link admission for a stable, host-controlled local directory.

    Resolve only macOS's two OS aliases before checking every component. On
    Windows realpath may expand an ordinary 8.3 name/change case; that spelling
    change is safe only after all original components reject reparse points.
    This is not an anchored sandbox against concurrent same-user replacement.
    """
    path = Path(os.path.abspath(directory))
    if sys.platform == 'darwin':
        for prefix, target in (('/var', '/private/var'), ('/tmp', '/private/tmp')):
            if str(path) == prefix or str(path).startswith(prefix + '/'):
                if os.path.realpath(prefix) != target:
                    raise ValueError('unexpected system directory alias')
                path = Path(target) / path.relative_to(prefix)
                break
    if len(path.parts) > 128:
        raise ValueError('directory depth bound')
    for component in (path, *path.parents):
        info = os.lstat(component)
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or getattr(info, 'st_file_attributes', 0) & 0x400):
            raise ValueError('directory aliases unsupported')
    return os.path.realpath(path)


def load_configuration_directory(directory, *, numbering_policy='explicit', module_runtime=None):
    return import_configuration(read_configuration_directory(directory),
                                numbering_policy=numbering_policy, module_runtime=module_runtime)


def read_configuration_directory(directory):
    """Read bounded, unchanged source bytes without choosing an active profile."""
    raw = os.fspath(directory)
    if type(raw) is not str or not raw or '\x00' in raw or raw.startswith(('//','\\\\')):
        raise ValueError('invalid configuration directory')
    try:
        root = _host_directory(raw)
    except OSError:
        raise ValueError('configuration source unavailable') from None
    files = {}; total = 0; directories = 0
    pending = [(root, '', 0)]
    try:
        while pending:
            path, relative, depth = pending.pop()
            directories += 1
            if directories > MAX_FILES or depth > 8:
                raise ValueError('configuration directory bound')
            with os.scandir(path) as iterator:
                entries = []
                for entry in iterator:
                    if len(entries) >= MAX_FILES:
                        raise ValueError("configuration directory entry bound")
                    entries.append(entry)
            if len(entries) > MAX_FILES:
                raise ValueError('configuration directory entry bound')
            for entry in entries:
                name = entry.name
                if name in ('.','..') or '\\' in name or ':' in name:
                    raise ValueError('unsafe configuration path')
                logical = relative + name
                # DirEntry.stat has zero identity/link fields on Windows. A fresh
                # no-follow stat preserves the same admission checks on all hosts.
                before = os.stat(entry.path, follow_symlinks=False)
                if getattr(before, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('configuration reparse point unsupported')
                if stat.S_ISDIR(before.st_mode):
                    pending.append((entry.path, logical+'/', depth+1));continue
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE_BYTES:
                    raise ValueError('unsupported configuration file')
                if len(files) >= MAX_FILES or total + before.st_size > MAX_TOTAL_BYTES:
                    raise ValueError('configuration file bound')
                fd = os.open(entry.path, os.O_RDONLY | getattr(os,'O_BINARY',0) | getattr(os,'O_NOFOLLOW',0))
                try:
                    opened = os.fstat(fd)
                    if not _path_matches_descriptor(before, opened) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                        raise ValueError('configuration source changed')
                    chunks=[]; remaining=MAX_FILE_BYTES+1
                    while remaining:
                        chunk=os.read(fd,min(65536,remaining))
                        if not chunk:break
                        chunks.append(chunk);remaining-=len(chunk)
                    content=b''.join(chunks)
                    after=os.fstat(fd)
                    path_after = os.stat(entry.path, follow_symlinks=False)
                    if (len(content) != before.st_size or _snapshot(after) != _snapshot(opened)
                            or _snapshot(path_after) != _snapshot(before)):
                        raise ValueError('configuration source changed')
                finally:os.close(fd)
                total+=len(content);files[logical]=content
    except OSError:
        raise ValueError('configuration source unavailable') from None
    return files
