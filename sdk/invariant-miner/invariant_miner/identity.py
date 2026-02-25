"""
invariant_miner/identity.py
==========================
Agent identity derivation for INVARIANT receipt generation.

Two identity paths:

  Software miner (most Bittensor miners)
  ─────────────────────────────────────
  agent_id = SHA-256(hotkey_ss58_utf8 || model_hash_bytes || reg_block_be_u64)

  Hardware / DePIN miner (ESP32-S3 eFuse-bound)
  ──────────────────────────────────────────────
  agent_id = Keccak-256(efuse_mac_bytes || chip_model_bytes)
  Ethereum-compatible — matches the SHA contract on Arbitrum Sepolia.

The returned agent_id is a 64-character lowercase hex string (32 bytes).
Store it at startup; it does not change unless model or registration changes.

Usage
-----
    from invariant_miner import derive_agent_id, derive_hardware_agent_id, hash_model

    model_hash = hash_model("my-model-v1")

    # Software miner (typical Bittensor case)
    agent_id = derive_agent_id(
        hotkey_ss58="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY",
        model_identifier="my-model-v1",
        registration_block=12345,
    )

    # Hardware / DePIN miner
    agent_id = derive_hardware_agent_id(
        efuse_mac_hex="aabbccddeeff",
        chip_model_hex="01",        # ESP32-S3 = 0x01
    )
"""

from __future__ import annotations

from invariant_miner._backend import (
    _derive_hardware_agent_id,
    _derive_software_agent_id,
    _hash_model,
)


def hash_model(identifier: str) -> str:
    """Derive a canonical 32-byte model hash from a model identifier string.

    The model hash is the SHA-256 of the UTF-8 encoded identifier string.
    Use a consistent, version-pinned identifier — e.g. ``"llama-3.2-1b-instruct-v1"``.
    This hash is registered in the validator's approved model list (Gate 2).

    Args:
        identifier: A unique, version-pinned string identifying the model.
                    Should be stable across restarts for the same model version.
                    Examples: ``"llama-3.2-1b-instruct-v1"``,
                              ``"gpt4all-falcon-q4_0"``,
                              ``"custom-finetuned-mistral-7b-2024-12"``

    Returns:
        64-character lowercase hex string (SHA-256 of the identifier).

    Example:
        >>> hash_model("llama-3.2-1b-instruct-v1")
        'a3f2...'   # deterministic 64-char hex
    """
    if not identifier or not identifier.strip():
        raise ValueError("model identifier must be a non-empty string")
    return _hash_model(identifier)


def derive_agent_id(
    hotkey_ss58: str,
    model_identifier: str,
    registration_block: int,
) -> str:
    """Derive the software miner agent_id for use in INVARIANT receipts.

    The agent_id is computed once at miner startup and stays constant
    for the lifetime of the registration:

        agent_id = SHA-256(hotkey_ss58_utf8 || model_hash_bytes || reg_block_be_u64)

    It is deterministic — the same inputs always produce the same agent_id.
    It is hotkey-bound — another miner cannot forge your agent_id without
    your private key, which makes cross-miner output copying detectable at Gate 1.

    Args:
        hotkey_ss58:        Your Bittensor hotkey in SS58 encoding.
                            Get it via: ``wallet.hotkey.ss58_address``
        model_identifier:   The human-readable model identifier string.
                            Must match exactly what you pass to ``hash_model()``.
                            Example: ``"llama-3.2-1b-instruct-v1"``
        registration_block: The Bittensor block number at which this hotkey
                            was registered on the INVARIANT subnet.
                            Get it via: ``subtensor.get_neuron_for_pubkey_and_subnet(
                                hotkey_ss58, netuid).block``

    Returns:
        64-character lowercase hex string (32-byte agent_id).

    Raises:
        ValueError: If any input is empty or registration_block is negative.

    Example:
        >>> derive_agent_id(
        ...     hotkey_ss58="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY",
        ...     model_identifier="llama-3.2-1b-instruct-v1",
        ...     registration_block=12345,
        ... )
        'b7c4e9...'  # deterministic 64-char hex
    """
    if not hotkey_ss58 or not hotkey_ss58.strip():
        raise ValueError("hotkey_ss58 must be a non-empty string")
    if not model_identifier or not model_identifier.strip():
        raise ValueError("model_identifier must be a non-empty string")
    if registration_block < 0:
        raise ValueError(f"registration_block must be >= 0, got {registration_block}")

    model_hash_hex = _hash_model(model_identifier)
    return _derive_software_agent_id(hotkey_ss58, model_hash_hex, registration_block)


def derive_agent_id_from_model_hash(
    hotkey_ss58: str,
    model_hash_hex: str,
    registration_block: int,
) -> str:
    """Derive the software miner agent_id when you already have the model_hash.

    Identical to :func:`derive_agent_id` but accepts a pre-computed
    ``model_hash_hex`` (64-char hex) instead of a model identifier string.
    Use this when you store the model_hash separately and want to avoid
    recomputing it.

    Args:
        hotkey_ss58:        Your Bittensor hotkey in SS58 encoding.
        model_hash_hex:     64-char hex string from :func:`hash_model`.
        registration_block: Block number at registration.

    Returns:
        64-character lowercase hex string (32-byte agent_id).

    Raises:
        ValueError: If model_hash_hex is not a valid 64-char hex string.
    """
    if not hotkey_ss58 or not hotkey_ss58.strip():
        raise ValueError("hotkey_ss58 must be a non-empty string")
    if len(model_hash_hex) != 64:
        raise ValueError(
            f"model_hash_hex must be 64 hex characters (32 bytes), "
            f"got {len(model_hash_hex)} chars"
        )
    try:
        bytes.fromhex(model_hash_hex)
    except ValueError as e:
        raise ValueError(f"model_hash_hex is not valid hex: {e}") from e
    if registration_block < 0:
        raise ValueError(f"registration_block must be >= 0, got {registration_block}")

    return _derive_software_agent_id(hotkey_ss58, model_hash_hex, registration_block)


def derive_hardware_agent_id(
    efuse_mac_hex: str,
    chip_model_hex: str,
) -> str:
    """Derive the DePIN hardware miner agent_id (Keccak-256).

    Used for ESP32-S3 or other hardware-bound miners where the identity
    is derived from silicon-level eFuse values that cannot be forged.

        agent_id = Keccak-256(efuse_mac_bytes || chip_model_bytes)

    This is Ethereum-compatible and matches the SHA contract on Arbitrum
    Sepolia (``0xD661a1aB8CEFaaCd78F4B968670C3bC438415615``).

    **Requires Keccak-256 support:**
    The Rust extension provides native Keccak-256. For the Python fallback,
    install ``pysha3`` or ``pycryptodome``. Without either, this function
    falls back to SHA-256 with a warning — do not use that in production.

    Args:
        efuse_mac_hex:  Hex string of the device eFuse MAC address.
                        Example: ``"aabbccddeeff"`` (6 bytes = 12 hex chars)
        chip_model_hex: Hex string identifying the chip model.
                        ESP32-S3 = ``"01"``

    Returns:
        64-character lowercase hex string (32-byte Keccak-256 agent_id).

    Raises:
        ValueError: If either input is not valid hex.

    Example:
        >>> derive_hardware_agent_id("aabbccddeeff", "01")
        'd4e2...'  # deterministic 64-char hex (Keccak-256)
    """
    if not efuse_mac_hex:
        raise ValueError("efuse_mac_hex must be a non-empty hex string")
    if not chip_model_hex:
        raise ValueError("chip_model_hex must be a non-empty hex string")
    try:
        bytes.fromhex(efuse_mac_hex)
    except ValueError as e:
        raise ValueError(f"efuse_mac_hex is not valid hex: {e}") from e
    try:
        bytes.fromhex(chip_model_hex)
    except ValueError as e:
        raise ValueError(f"chip_model_hex is not valid hex: {e}") from e

    return _derive_hardware_agent_id(efuse_mac_hex, chip_model_hex)
