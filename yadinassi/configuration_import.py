"""Bounded host-directory reader for official XML/BSL configuration packages."""
import os
import stat
from .configuration_xml import import_configuration, MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES


def load_configuration_directory(directory):
    raw = os.fspath(directory)
    if type(raw) is not str or not raw or '\x00' in raw or raw.startswith(('//','\\\\')):
        raise ValueError('invalid configuration directory')
    root = os.path.abspath(raw)
    if os.path.realpath(root) != root:
        raise ValueError('configuration directory aliases unsupported')
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
                before = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(before.st_mode):
                    pending.append((entry.path, logical+'/', depth+1));continue
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE_BYTES:
                    raise ValueError('unsupported configuration file')
                if len(files) >= MAX_FILES or total + before.st_size > MAX_TOTAL_BYTES:
                    raise ValueError('configuration file bound')
                fd = os.open(entry.path, os.O_RDONLY | getattr(os,'O_BINARY',0) | getattr(os,'O_NOFOLLOW',0))
                try:
                    opened = os.fstat(fd)
                    if (opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns) != (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                        raise ValueError('configuration source changed')
                    chunks=[]; remaining=MAX_FILE_BYTES+1
                    while remaining:
                        chunk=os.read(fd,min(65536,remaining))
                        if not chunk:break
                        chunks.append(chunk);remaining-=len(chunk)
                    content=b''.join(chunks)
                    after=os.fstat(fd)
                    if len(content)!=before.st_size or (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)!=(opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns):
                        raise ValueError('configuration source changed')
                finally:os.close(fd)
                total+=len(content);files[logical]=content
    except OSError:
        raise ValueError('configuration source unavailable') from None
    return import_configuration(files)
