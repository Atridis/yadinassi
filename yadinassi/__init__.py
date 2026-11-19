"""Public embedding API for the BSL interpreter."""

from .types.errors import BSLError, BSLRuntimeError
from .runtime import Interpreter

__all__ = ["BSLError", "BSLRuntimeError", "Interpreter"]
__version__ = "0.5.1"
