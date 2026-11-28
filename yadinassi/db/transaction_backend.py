"""Host transaction requests. Tickets denote staging, never durable Write success.

This API does not join standalone BSL object Write calls into a transaction.
"""
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TransactionRequest:
    kind: str
    draft: object
    expected: object = None


@dataclass(frozen=True, slots=True)
class StagedTicket:
    operation_id: UUID
    index: int
    kind: str


@dataclass(frozen=True, slots=True)
class TransactionOutcome:
    ticket: StagedTicket
    result: object
