"""Public embedding API for the BSL interpreter."""

from .errors import BSLError
from .runtime import Interpreter

__all__ = ["BSLError", "Interpreter"]
__version__ = "0.2.0"
