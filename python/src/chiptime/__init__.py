"""chiptime — recovery-grade FIT file processing.

Parse anything, lose nothing silently, explain everything.

    import chiptime
    result = chiptime.parse("ride.fit")          # lenient by default
    result.ok, result.file_type, result.recovery
    result.to_canonical_json()                    # deterministic (RFC 8785)
"""

from chiptime._api import iter_frames, iter_messages, parse
from chiptime.edit import EditError, EditResult, edit
from chiptime.errors import (
    CrcMismatchError,
    EmptyFileError,
    FitError,
    HeaderError,
    NotFitError,
    ProtocolError,
    TruncatedError,
)
from chiptime.repair import NotRepairableError, RepairResult, repair
from chiptime.result import Mode, ParseResult

__version__ = "0.5.0"

__all__ = [
    "CrcMismatchError",
    "EditError",
    "EditResult",
    "EmptyFileError",
    "FitError",
    "HeaderError",
    "Mode",
    "NotFitError",
    "NotRepairableError",
    "ParseResult",
    "ProtocolError",
    "RepairResult",
    "TruncatedError",
    "__version__",
    "edit",
    "iter_frames",
    "iter_messages",
    "parse",
    "repair",
]
