"""Portable, inert shell-dispatch fixture shared by ordinary native CI tests."""
import os
from pathlib import Path, PureWindowsPath
import shutil
import subprocess


def bash_executable(*, platform=None, which=None, is_file=None):
    """Use an actual Bash, never the Windows System32 WSL launcher."""
    platform=os.name if platform is None else platform
    which=shutil.which if which is None else which
    is_file=(lambda value:Path(value).is_file()) if is_file is None else is_file
    if platform not in ('nt','posix'):raise AssertionError('Unsupported shell fixture platform')
    if platform=='nt':
        git=which('git.exe') or which('git')
        executable=PureWindowsPath(git) if git else None
        if (executable is not None and executable.is_absolute()
                and executable.name.lower()=='git.exe'
                and executable.parent.name.lower() in ('cmd','bin')):
            # Git-for-Windows normally exposes cmd/git.exe (or bin/git.exe).
            root=executable.parent.parent
            for relative in ('bin/bash.exe','usr/bin/bash.exe'):
                candidate=str(root/relative)
                if is_file(candidate):return candidate
        raise AssertionError('Git-for-Windows Bash is required for actual workflow dispatch')
    bash=which('bash')
    if not bash:raise AssertionError('Bash is required for actual workflow dispatch')
    return bash


def dispatch(script):
    # Shell function avoids a CRLF-sensitive shebang, chmod and host PATH
    # translation. Bash itself still executes the unchanged workflow branches.
    stub="python3() { printf '%s\\n' \"$*\"; }\n"
    env={key:value for key,value in os.environ.items() if key not in ('BASH_ENV','ENV')}
    return subprocess.run([bash_executable(),'--noprofile','--norc','-e','-c',stub+script],
        env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=10)
