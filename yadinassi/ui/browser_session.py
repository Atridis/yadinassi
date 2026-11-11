"""Bounded, process-local browser attachments, not business/form sessions.

Only the current writer generation may dispatch RPC. Detach never writes,
discards or invokes BSL lifecycle. The host decides whether idle shutdown is
safe; a missing heartbeat cannot manufacture a successful business outcome.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import re
import secrets
from threading import Lock
import time


PROTOCOL = 'yadinassi-browser-attachment/1'
MAX_ATTACHMENTS = 256
LEASE_SECONDS = 90
GRACE_SECONDS = 30
RESUME_SECONDS = 24 * 60 * 60
_TOKEN = re.compile(r'[A-Za-z0-9_-]{32,128}\Z')
_INSTANCE = re.compile(r'[0-9a-f]{32}\Z')


class AttachmentError(ValueError):
    """A fixed public refusal before any business dispatch."""


@dataclass
class _Attachment:
    identity: str
    credential: str
    resume: str
    instance: str
    seen: float
    pending: bool = False
    detached: bool = False


class BrowserSession:
    def __init__(self, launcher_token, *, clock=time.monotonic,
                 lease_seconds=LEASE_SECONDS, grace_seconds=GRACE_SECONDS):
        if type(launcher_token) is not str or not _TOKEN.fullmatch(launcher_token):
            raise ValueError('invalid launcher capability')
        if (type(lease_seconds) is not int or not 10 <= lease_seconds <= 3600
                or type(grace_seconds) is not int or not 1 <= grace_seconds <= 3600):
            raise ValueError('invalid attachment lifetime')
        self._launcher = launcher_token
        self._clock = clock
        self.lease_seconds = lease_seconds
        self.grace_seconds = grace_seconds
        self._gate = Lock()
        self._attachments = {}
        self._resumes = {}
        self._admissions = {}
        self._writer = None
        self._generation = 0
        self._absent_since = None
        self._started = False
        self._closed = False
        self._uncertain = False
        self._shutdown_refused = False

    @contextmanager
    def _locked(self):
        if not self._gate.acquire(blocking=False):
            raise AttachmentError('busy')
        try:
            yield
        finally:
            self._gate.release()

    def _live(self, item, now):
        return not item.detached and now - item.seen < self.lease_seconds

    def _expire(self):
        now = self._clock()
        if self._writer is not None and not self._live(self._attachments[self._writer], now):
            self._writer = None
            self._generation += 1  # Fence an expired writer before admitting any new work.
        if self._started and not any(self._live(a, now) for a in self._attachments.values()):
            if self._absent_since is None:
                self._absent_since = now
        else:
            self._absent_since = None
        return now

    def _authenticate(self, token, attachment):
        item = self._attachments.get(attachment) if type(attachment) is str else None
        if (item is None or type(token) is not str or not _TOKEN.fullmatch(token)
                or not secrets.compare_digest(item.credential, token)):
            raise AttachmentError('unauthorized')
        return item

    def _status(self, item, *, issued=False):
        result = {'protocol': PROTOCOL, 'attachment': item.identity,
                  'role': 'writer' if self._writer == item.identity else 'observer',
                  'generation': self._generation, 'leaseSeconds': self.lease_seconds,
                  'graceSeconds': self.grace_seconds,
                  'recovery': self._uncertain or self._shutdown_refused
                      or any(a.pending for a in self._attachments.values()),
                  'closed': self._closed}
        if issued:
            result.update(credential=item.credential, resume=item.resume)
        return result

    def attach(self, token, instance):
        with self._locked():
            now = self._expire()
            if self._closed:
                raise AttachmentError('closed')
            if type(instance) is not str or not _INSTANCE.fullmatch(instance):
                raise AttachmentError('invalid_message')
            if type(token) is not str or not _TOKEN.fullmatch(token):
                raise AttachmentError('unauthorized')
            launcher = secrets.compare_digest(token, self._launcher)
            previous = self._resumes.get(token)
            if not launcher and (previous is None or now - previous.seen >= RESUME_SECONDS):
                raise AttachmentError('unauthorized')
            # A repeated bootstrap is not a business retry and must not allocate
            # unlimited tabs after a lost attachment response.
            admitted = self._admissions.get((token, instance))
            if admitted is not None:
                return self._status(admitted, issued=True)
            if len(self._attachments) >= MAX_ATTACHMENTS:
                raise AttachmentError('capacity')
            identity = 'attachment-' + str(len(self._attachments) + 1)
            item = _Attachment(identity, secrets.token_urlsafe(32), secrets.token_urlsafe(32), instance, now)
            self._attachments[identity] = item
            self._resumes[item.resume] = item
            self._admissions[token, instance] = item
            self._started = True
            if self._writer is None and not self._uncertain:
                self._generation += 1
                self._writer = identity
            self._absent_since = None
            return self._status(item, issued=True)

    def command(self, token, attachment, action, generation, pending):
        with self._locked():
            now = self._expire()
            item = self._authenticate(token, attachment)
            if (action not in ('status', 'heartbeat', 'detach', 'takeover')
                    or type(generation) is not int or not 0 <= generation <= 2**53 - 1
                    or type(pending) is not bool):
                raise AttachmentError('invalid_message')
            if self._closed:
                return self._status(item)
            if action == 'takeover':
                if self._uncertain:
                    raise AttachmentError('outcome_unknown')
                if generation != self._generation:
                    raise AttachmentError('stale_generation')
                self._generation += 1
                self._writer = item.identity
                self._shutdown_refused = False
            if action != 'status':
                item.pending = pending
                item.seen = now
                item.detached = action == 'detach'
                if item.detached and self._writer == item.identity:
                    self._writer = None
                    self._generation += 1
            self._expire()
            return self._status(item)

    @contextmanager
    def dispatch(self, token, attachment, generation):
        """Hold the ownership fence across the entire admitted business request.

        Refusals happen before yielding; an exception after yield has an unknown
        outcome and locks the host, never granting a new writer to retry it.
        """
        with self._locked():
            now = self._expire()
            item = self._authenticate(token, attachment)
            if self._closed:
                raise AttachmentError('closed')
            if self._uncertain:
                raise AttachmentError('outcome_unknown')
            if (type(generation) is not int or generation != self._generation
                    or self._writer != item.identity or not self._live(item, now)):
                raise AttachmentError('not_writer')
            item.seen = now
            try:
                yield
            except BaseException:
                self._uncertain = True
                raise

    def mark_closed(self):
        # Called while dispatch or idle_shutdown holds the gate.
        self._closed = True
        self._writer = None
        self._generation += 1

    def idle_shutdown(self, close_if_safe):
        """Ask trusted host policy to close; never infer safety from browser flags."""
        with self._locked():
            now = self._expire()
            if (self._closed or self._uncertain or self._shutdown_refused
                    or self._absent_since is None or now - self._absent_since < self.grace_seconds
                    or any(a.pending for a in self._attachments.values())):
                return False
            try:
                closed = close_if_safe()
            except BaseException:
                self._uncertain = True
                raise
            if type(closed) is not bool:
                self._uncertain = True
                raise ValueError('invalid host shutdown verdict')
            if closed:
                self.mark_closed()
            else:
                self._shutdown_refused = True
            return closed
