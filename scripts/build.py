"""Build and archive one native executable. Run on each target OS/architecture."""

import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import zipfile


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
    args = parser.parse_args()
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
        archive = ROOT / "dist" / f"yadinassi-{host}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path, name in files:
                bundle.write(path, name)
    else:
        archive = ROOT / "dist" / f"yadinassi-{host}.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for path, name in files:
                bundle.add(path, arcname=name)
    print(f"Built and verified: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
