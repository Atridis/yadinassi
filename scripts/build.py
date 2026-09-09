"""Build and archive one native executable. Run on each target OS/architecture."""

import argparse
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import zipfile

from yadinassi import __version__


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    ("Windows", "AMD64"): "windows",
    ("Windows", "x86_64"): "windows",
    ("Linux", "x86_64"): "linux",
    ("Darwin", "x86_64"): "mac-x86",
    ("Darwin", "arm64"): "mac-arm",
}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build a self-contained yadinassi executable")
    parser.add_argument("--target", choices=sorted(set(TARGETS.values())),
                        help="validate native target; does not enable cross-compilation")
    parser.add_argument("--release-tag", default=os.environ.get("YADINASSI_RELEASE_TAG"),
                        help="validate release tag against the project version (e.g. v0.2.0)")
    args = parser.parse_args()
    version = __version__
    if not re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", version):
        parser.error("Invalid project version in yadinassi/__init__.py")
    if args.release_tag and args.release_tag != f"v{version}":
        parser.error(f"Release tag {args.release_tag!r} does not match project version {version!r}; "
                     f"expected v{version}. Update __version__ in yadinassi/__init__.py before tagging.")
    host = TARGETS.get((platform.system(), platform.machine()))
    if host is None:
        parser.error(f"Unsupported build host: {platform.system()} {platform.machine()}")
    if args.target is not None and args.target != host:
        parser.error(f"Target {args.target} requires its own runner; this host builds {host}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build" / "pyinstaller-cache")
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--console", "--name", "yadinassi", "--noupx",
        "--paths", str(ROOT),
        "--distpath", str(ROOT / "dist" / host),
        "--workpath", str(ROOT / "build" / host),
        "--specpath", str(ROOT / "build"),
    ]
    if platform.system() == "Darwin":
        command += ["--target-architecture", platform.machine()]
    command.append(str(ROOT / "scripts" / "entrypoint.py"))
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    executable = ROOT / "dist" / host / ("yadinassi.exe" if host == "windows" else "yadinassi")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke_test.py"), str(executable)],
                   cwd=ROOT, env=env, check=True)
    files = [(executable, executable.name), (ROOT / "README.md", "README.md"),
             (ROOT / "LICENSE", "LICENSE"), (ROOT / "code_samples" / "basic.bsl", "basic.bsl")]
    if host == "windows":
        archive = ROOT / "dist" / f"yadinassi-{version}-{host}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path, name in files:
                bundle.write(path, name)
    else:
        archive = ROOT / "dist" / f"yadinassi-{version}-{host}.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for path, name in files:
                bundle.add(path, arcname=name)
    print(f"Built and verified: {archive}")
    if output_file := os.environ.get("GITHUB_OUTPUT"):
        with open(output_file, "a", encoding="utf-8") as output:
            output.write(f"archive-path={archive.relative_to(ROOT).as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
