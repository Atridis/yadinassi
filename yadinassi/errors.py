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
