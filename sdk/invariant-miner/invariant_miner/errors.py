"""
invariant_miner/errors.py
========================
Exception hierarchy for the invariant-miner SDK.

All exceptions raised by invariant_miner are subclasses of InvariantError
so callers can catch the entire SDK with a single except clause:

    try:
        receipt = build_receipt(...)
    except InvariantError as e:
        logger.error("INVARIANT SDK error: %s", e)
"""

from __future__ import annotations


class InvariantError(Exception):
    """Base class for all invariant-miner exceptions."""


class ReceiptBuildError(InvariantError):
    """Raised when receipt construction fails.

    Common causes:
    - Invalid agent_id (wrong length, not hex)
    - Negative counter or tempo_id
    - Backend (Rust or Python) raised an unexpected error
    """


class CounterRollbackError(InvariantError):
    """Raised when a counter value would cause a Gate 3 failure.

    This is raised proactively by the counter manager when you attempt
    to build a receipt with a counter that is not strictly greater than
    the last confirmed counter for this agent.

    Attributes
    ----------
    agent_id : str
        The agent_id hex string that owns the counter.
    attempted : int
        The counter value that was attempted.
    last_confirmed : int
        The last confirmed counter value on the validator side.
    """

    def __init__(self, agent_id: str, attempted: int, last_confirmed: int) -> None:
        self.agent_id = agent_id
        self.attempted = attempted
        self.last_confirmed = last_confirmed
        super().__init__(
            f"Counter rollback detected for agent {agent_id[:12]}…: "
            f"attempted={attempted}, last_confirmed={last_confirmed}. "
            f"Counter must be strictly greater than last_confirmed. "
            f"Use counter={last_confirmed + 1} or higher."
        )


class RegistryError(InvariantError):
    """Raised for registry load/save/query errors."""


class VerifierError(InvariantError):
    """Raised for verifier initialisation or state errors."""


class BackendError(InvariantError):
    """Raised when the backend (Rust or Python) encounters an unexpected error."""
