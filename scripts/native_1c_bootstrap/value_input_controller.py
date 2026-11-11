"""Bounded real keys on a private, PID-bound native acquisition display.

No dependency installation, user-display fallback, callback invocation or text
extraction. Unknown focus/window/process identity is a closed acquisition error.
"""
import ctypes as C
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import full_suite as full
from value_input_packet import OWNERSHIP_REASONS, valid_controller_diagnostic

MAX_WINDOWS = 512
MAX_DEPTH = 8
MAX_POLLS = 2400
MAX_KEYS = 48
TITLES = tuple('YADINASSI-VI0' + str(i) + '-' for i in range(1, 9))
PLANS = (('Control_L+a', 'e', 'd', 'i', 't', 'e', 'd', 'Return'),
         ('Return',), ('Return',), ('Return',), ('Escape',),
         ('Return',), ('Escape',), ('Control_L+a', 'BackSpace', 'Return'))


class OwnershipError(ValueError):
    pass


class ControllerFailure(full.FullError):
    """Closed evidence only; the original exception is never serialized."""
    def __init__(self, error, phase, completed):
        code = 'unexpected_exception'
        kind = 'unexpected_failure'
        if type(error) is OwnershipError:
            reason = error.args[0] if len(error.args) == 1 else None
            if type(reason) is str and reason in OWNERSHIP_REASONS:
                code = reason.lower().replace(' ', '_')
                kind = 'process_failed'
        elif isinstance(error, OSError):
            code = 'os_error'
        elif isinstance(error, full.FullError):
            code = 'runner_error'
            kind = error.kind
        diagnostic = {'phase': phase, 'code': code, 'completed_actions': completed}
        if not valid_controller_diagnostic(diagnostic):
            diagnostic = {'phase': 'preflight', 'code': 'unexpected_exception', 'completed_actions': 0}
            kind = 'unexpected_failure'
        self.diagnostic = diagnostic
        super().__init__(kind)


def process_identity(pid):
    if type(pid) is not int or pid <= 1:
        raise OwnershipError('process identity')
    raw = (Path('/proc') / str(pid) / 'stat').read_bytes()
    if len(raw) > 4096 or b') ' not in raw:
        raise OwnershipError('process identity')
    fields = raw.rsplit(b') ', 1)[1].split()
    if len(fields) < 20 or fields[0] == b'Z':
        raise OwnershipError('process identity')
    return int(fields[2]), int(fields[3]), int(fields[19])  # pgrp, session, starttime


class Display:
    def __init__(self):
        if os.environ.get('DISPLAY') != ':99' or os.environ.get('XAUTHORITY') != '/tmp/onec-smoke/xauth':
            raise OwnershipError('private display required')
        auth = Path('/tmp/onec-smoke/xauth')
        if auth.is_symlink() or not auth.is_file() or auth.stat().st_uid != os.getuid():
            raise OwnershipError('private authority required')
        self.x = C.CDLL('libX11.so.6')
        self.xt = C.CDLL('libXtst.so.6')
        U, P = C.c_ulong, C.c_void_p
        signatures = {
            'XOpenDisplay': ([C.c_char_p], P), 'XCloseDisplay': ([P], C.c_int),
            'XDefaultRootWindow': ([P], U), 'XInternAtom': ([P, C.c_char_p, C.c_int], U),
            'XGetWindowProperty': ([P,U,U,C.c_long,C.c_long,C.c_int,U,C.POINTER(U),C.POINTER(C.c_int),C.POINTER(U),C.POINTER(U),C.POINTER(P)], C.c_int),
            'XQueryTree': ([P,U,C.POINTER(U),C.POINTER(U),C.POINTER(C.POINTER(U)),C.POINTER(C.c_uint)], C.c_int),
            'XGetInputFocus': ([P,C.POINTER(U),C.POINTER(C.c_int)], C.c_int),
            'XSetInputFocus': ([P,U,C.c_int,U], C.c_int),
            'XStringToKeysym': ([C.c_char_p], U), 'XKeysymToKeycode': ([P,U], C.c_ubyte),
            'XSync': ([P,C.c_int], C.c_int), 'XFree': ([P], C.c_int),
            'XGrabServer': ([P], C.c_int), 'XUngrabServer': ([P], C.c_int),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.x, name); function.argtypes = args; function.restype = result
        self.xt.XTestFakeKeyEvent.argtypes = [P,C.c_uint,C.c_int,U]
        self.xt.XTestFakeKeyEvent.restype = C.c_int
        self.xt.XTestQueryExtension.argtypes = [P,*([C.POINTER(C.c_int)] * 4)]
        self.xt.XTestQueryExtension.restype = C.c_int
        self.error = False
        self._error_type = C.CFUNCTYPE(C.c_int, P, P)
        def error(display, event):
            self.error = True
            return 0
        self._handler = self._error_type(error)
        self.x.XSetErrorHandler.argtypes = [self._error_type]
        self.x.XSetErrorHandler.restype = P
        self._previous_handler = self.x.XSetErrorHandler(self._handler)
        self.display = self.x.XOpenDisplay(b':99')
        if not self.display:
            self.x.XSetErrorHandler(C.cast(self._previous_handler,self._error_type))
            raise OwnershipError('private display unavailable')
        fields = [C.c_int() for _ in range(4)]
        if not self.xt.XTestQueryExtension(self.display, *(C.byref(x) for x in fields)):
            self.close(); raise OwnershipError('XTest unavailable')
        self.root = self.x.XDefaultRootWindow(self.display)
        self.keys = 0

    def close(self):
        if self.display:
            self.x.XCloseDisplay(self.display); self.display = None
            self.x.XSetErrorHandler(C.cast(self._previous_handler,self._error_type))

    def sync(self):
        self.x.XSync(self.display, 0)
        if self.error:
            raise OwnershipError('window changed')

    def property(self, window, name):
        atom = self.x.XInternAtom(self.display, name, 1)
        if not atom:
            return None
        actual, count, rest = C.c_ulong(), C.c_ulong(), C.c_ulong()
        format_ = C.c_int(); pointer = C.c_void_p()
        code = self.x.XGetWindowProperty(self.display,window,atom,0,256,0,0,
            C.byref(actual),C.byref(format_),C.byref(count),C.byref(rest),C.byref(pointer))
        self.sync()
        try:
            if code or rest.value or count.value > 1024:
                raise OwnershipError('window property limit')
            if not pointer.value or not actual.value:
                return None
            if format_.value == 8:
                return C.string_at(pointer, count.value)
            if format_.value == 32 and count.value == 1:
                return C.cast(pointer,C.POINTER(C.c_ulong))[0]
            raise OwnershipError('window property shape')
        finally:
            if pointer.value: self.x.XFree(pointer)

    def tree(self, window):
        root, parent = C.c_ulong(), C.c_ulong()
        children = C.POINTER(C.c_ulong)(); count = C.c_uint()
        ok = self.x.XQueryTree(self.display,window,C.byref(root),C.byref(parent),C.byref(children),C.byref(count))
        self.sync()
        try:
            if not ok or count.value > MAX_WINDOWS:
                raise OwnershipError('window tree limit')
            return parent.value, tuple(children[i] for i in range(count.value))
        finally:
            if children: self.x.XFree(children)

    def title(self, window):
        raw = self.property(window,b'_NET_WM_NAME')
        if raw is None: raw = self.property(window,b'WM_NAME')
        return raw

    def find(self, title):
        pending = [(self.root,0)]; count = 0; found = []
        while pending:
            window, depth = pending.pop(); count += 1
            if count > MAX_WINDOWS or depth > MAX_DEPTH:
                raise OwnershipError('window tree limit')
            if self.title(window) == title: found.append(window)
            _, children = self.tree(window)
            if count + len(pending) + len(children) > MAX_WINDOWS:
                raise OwnershipError('window tree limit')
            pending.extend((child,depth+1) for child in children)
        if len(found) > 1: raise OwnershipError('ambiguous owned window')
        return found[0] if found else None

    def owned(self, window, title, leader, identity, executable):
        if process_identity(leader) != identity or self.title(window) != title:
            raise OwnershipError('owned window changed')
        pid = self.property(window,b'_NET_WM_PID')
        if type(pid) is not int or pid <= 1:
            raise OwnershipError('window PID unavailable')
        group, session, _ = process_identity(pid)
        if (group != leader or session != leader
                or (Path('/proc') / str(pid) / 'exe').resolve() != executable):
            raise OwnershipError('window process mismatch')

    def focused(self, window):
        focus, revert = C.c_ulong(), C.c_int()
        self.x.XGetInputFocus(self.display,C.byref(focus),C.byref(revert)); self.sync()
        current = focus.value
        for _ in range(MAX_DEPTH + 1):
            if current == window: return
            if current in (0,1,self.root): break
            current, _ = self.tree(current)
        raise OwnershipError('focus outside owned dialog')

    def drive(self, window, title, leader, identity, executable, plan):
        self.owned(window,title,leader,identity,executable)
        self.x.XSetInputFocus(self.display,window,1,0); self.sync()
        self.focused(window)
        for chord in plan:
            codes = []
            for name in chord.split('+'):
                sym = self.x.XStringToKeysym(name.encode('ascii'))
                code = self.x.XKeysymToKeycode(self.display,sym)
                if not sym or not code: raise OwnershipError('key unavailable')
                codes.append(code)
            # Private display only. Hold the server for this bounded chord so
            # another client cannot switch focus/unmap between verification and
            # the queued press/release. Always release before waiting or polling.
            if len(codes) > 2:
                raise OwnershipError('chord budget')
            pressed = []
            self.x.XGrabServer(self.display)
            try:
                self.owned(window,title,leader,identity,executable); self.focused(window)
                for code in codes:
                    self.keys += 1
                    if self.keys > MAX_KEYS: raise OwnershipError('key budget')
                    # Retain even an uncertain failed enqueue for cleanup.
                    pressed.append(code)
                    if not self.xt.XTestFakeKeyEvent(self.display,code,1,0):
                        raise OwnershipError('key delivery failed')
                while pressed:
                    if not self.xt.XTestFakeKeyEvent(self.display,pressed[-1],0,0):
                        raise OwnershipError('key delivery failed')
                    pressed.pop()
            finally:
                primary = sys.exc_info()[1]
                cleanup_error = None
                # At most two retained keycodes; release before ungrabbing so
                # failure cannot leave a sticky modifier in the owned display.
                for code in reversed(pressed):
                    try:
                        if not self.xt.XTestFakeKeyEvent(self.display,code,0,0):
                            raise OwnershipError('key release failed')
                    except BaseException as error:
                        if cleanup_error is None: cleanup_error = error
                try:
                    self.x.XUngrabServer(self.display)
                except BaseException as error:
                    if cleanup_error is None: cleanup_error = error
                try:
                    self.sync()
                except BaseException as error:
                    if cleanup_error is None: cleanup_error = error
                if primary is None and cleanup_error is not None:
                    raise cleanup_error
            time.sleep(0.03)


def _run_owned(command, directory, log, nonce, state):
    if (os.name != 'posix' or not re.fullmatch('[0-9a-f]{32}',nonce)
            or directory != Path('/tmp/onec-smoke') / ('stage3-' + nonce)
            or command.count('/C') != 1 or command[command.index('/C')+1] != str(directory/'request.json')):
        raise full.FullError('invalid_input')
    full.absent(log)
    executable = Path(command[0]).resolve(strict=True)
    state['phase'] = 'display'
    display = Display()
    completed = 0
    try:
        state['phase'] = 'launch'
        with log.open('xb') as output, subprocess.Popen(command,cwd=directory,
                stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                start_new_session=True) as child:
            try:
                state['phase'] = 'identity'
                identity = process_identity(child.pid)
                if identity[:2] != (child.pid,child.pid): raise OwnershipError('session identity')
                deadline = time.monotonic() + 120
                for _ in range(MAX_POLLS):
                    state['phase'] = 'poll'
                    if child.poll() is not None: break
                    if time.monotonic() >= deadline: raise OwnershipError('input deadline')
                    if completed < len(PLANS):
                        title = (TITLES[completed]+nonce).encode('ascii')
                        window = display.find(title)
                        if window is not None:
                            state['phase'] = 'drive'
                            display.drive(window,title,child.pid,identity,executable,PLANS[completed])
                            completed += 1
                            state['completed'] = completed
                    time.sleep(0.05)
                state['phase'] = 'exit'
                if child.poll() is None or child.returncode != 0 or completed != 8:
                    raise OwnershipError('incomplete owned input execution')
                # A normally exiting leader must not leave detached descendants.
                quiet_deadline = time.monotonic() + 5
                while True:
                    try: os.killpg(child.pid,0)
                    except ProcessLookupError: break
                    if time.monotonic() >= quiet_deadline:
                        raise OwnershipError('surviving input process')
                    time.sleep(0.02)
            except BaseException:
                failed_phase = state['phase']
                state['phase'] = 'process_cleanup'
                full._stop_group(child)
                state['phase'] = failed_phase
                raise
    finally:
        failed_phase = state['phase']
        state['phase'] = 'display_cleanup'
        display.close()
        state['phase'] = failed_phase
    return completed


def run_owned(command, directory, log, nonce):
    state = {'phase': 'preflight', 'completed': 0}
    try:
        return _run_owned(command, directory, log, nonce, state)
    except Exception as error:
        raise ControllerFailure(error, state['phase'], state['completed']) from None
