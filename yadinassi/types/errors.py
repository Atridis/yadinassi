"""Source-aware errors shared by all interpreter stages."""


class BSLError(Exception):
    def __init__(self, message: str, source: str, line: int, column: int):
        super().__init__(message)
        self.message = message
        self.source = source
        self.line = line
        self.column = column

    def __str__(self) -> str:
        return f"{self.source}:{self.line}:{self.column}: {self.message}"


class IncompleteInput(BSLError):
    """The parser needs more input; used by the multiline REPL."""


class BSLRuntimeError(BSLError):
    """A recoverable execution error, catchable by BSL Try/Except."""

    def __init__(self, message: str, source: str, line: int, column: int, *, info=None, source_line=""):
        super().__init__(message, source, line, column)
        # Keep the snapshot on the error so rethrow and routine propagation keep it.
        self.info = info
        self.source_line = source_line
