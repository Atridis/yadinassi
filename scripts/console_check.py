"""POSIX terminal regression check shared by source and frozen binary tests."""

import os
import re
import subprocess
import time


def check_console(command: list[str], *, cwd, env=None) -> str:
    # Imports stay local so the build scripts can also be used on Windows.
    import errno
    import fcntl
    import pty
    import select
    import struct
    import termios

    master, slave = pty.openpty()
    attributes = termios.tcgetattr(slave)
    attributes[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, attributes)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))
    terminal_env = dict(os.environ if env is None else env)
    terminal_env["TERM"] = "xterm"
    terminal_env["PROMPT_TOOLKIT_NO_CPR"] = "1"
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave,
                               cwd=cwd, env=terminal_env)
    os.close(slave)
    data = bytearray()
    position = 0

    def read_output() -> bool:
        if not select.select([master], [], [], 0.1)[0]:
            return process.poll() is None
        try:
            chunk = os.read(master, 65536)
        except OSError as error:
            if error.errno == errno.EIO:
                return False
            raise
        data.extend(chunk)
        return bool(chunk)

    def expect(text: str) -> None:
        nonlocal position
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            found = data.find(text.encode(), position)
            if found >= 0:
                position = found + len(text)
                return
            if not read_output():
                break
        raise AssertionError(f"Console did not show {text!r}: {data.decode('utf-8', errors='replace')}")

    def send(prompt: str, keys: str) -> None:
        # The renderer can replace trailing spaces with cursor movement.
        expect(prompt.rstrip())
        os.write(master, keys.encode("utf-8"))
        # Each completed prompt disables bracketed paste; redraws do not.
        expect("\x1b[?2004l")

    def corrected_line(message: str) -> str:
        text = f'Соообщить("{message}");'
        # Move to the extra Cyrillic letter, step right, then delete it.
        return text + "\x1b[D" * (len(text) - 2) + "\x1b[C\x7f\n"

    try:
        send(">>> ", corrected_line("Курсор"))
        send(">>> ", "\x1b[A\n")  # Recall and execute the corrected line.
        send(">>> ", '\x1b[A\x1b[BСообщить("Вниз");\n')
        send(">>> ", "Если Истина Тогда\n")
        send("... ", corrected_line("Блок"))
        send("... ", "КонецЕсли;\n")
        send(">>> ", "/exit\n")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and read_output():
            pass
        code = process.wait(timeout=2)
        output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", data.decode("utf-8"))
        if code != 0 or "Traceback" in output or "^[[D" in output:
            raise AssertionError(f"Console failed ({code}): {output}")
        for message, count in (("Курсор", 2), ("Вниз", 1), ("Блок", 1)):
            if output.count(f"\r\n{message}\r\n") != count:
                raise AssertionError(f"Unexpected console output for {message!r}: {output}")
        return output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
