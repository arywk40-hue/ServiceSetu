"""Dorado-only native FET invoice and on-chain transfer verification."""
from __future__ import annotations

import os
import re
from decimal import Decimal

from .core import Rejected

NETWORK = "dorado-1"
DENOM = "atestfet"
DECIMALS = 18
ATOMIC_PER_FET = 10 ** DECIMALS
PAYMENT_METHOD = "fet_direct"


def fet_amount(value: str | Decimal | None = None) -> tuple[str, int]:
    raw = str(value if value is not None else os.getenv("FET_TEST_AMOUNT", "0.1")).strip()
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?", raw):
        raise Rejected("FET_TEST_AMOUNT must be a positive decimal with at most 18 places")
    whole, _, fraction = raw.partition('.')
    fraction = fraction.ljust(DECIMALS, '0')
    # Integer parsing is independent of the process-wide Decimal precision.
    atomic = int(whole) * ATOMIC_PER_FET + int(fraction)
    if atomic <= 0:
        raise Rejected("FET_TEST_AMOUNT must be greater than zero and fit atestfet precision")
    return f"{int(whole)}.{fraction}", atomic


def deadline_seconds(value: str | None = None) -> int:
    raw=value if value is not None else os.getenv('FET_PAYMENT_DEADLINE_SECONDS','300')
    if not re.fullmatch(r'[0-9]+',str(raw).strip()):raise Rejected('FET_PAYMENT_DEADLINE_SECONDS must be a positive whole number')
    seconds=int(raw)
    if not 1<=seconds<=3600:raise Rejected('FET_PAYMENT_DEADLINE_SECONDS must be between 1 and 3600')
    return seconds


def native_address(value: str) -> bool:
    """Accept a checksummed native fetch1 bech32 address, never agent1."""
    if not isinstance(value, str) or not value.startswith("fetch1"):
        return False
    try:
        from bech32 import bech32_decode
        hrp, data = bech32_decode(value)
    except (ImportError, ValueError):
        return False
    return hrp == "fetch" and data is not None


def transaction_hash(value: str) -> str:
    if not isinstance(value, str):
        raise Rejected("Provide the Dorado transaction hash")
    candidate = value.removeprefix("0x").removeprefix("0X")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", candidate):
        raise Rejected("Dorado transaction hash must be 64 hexadecimal characters")
    return candidate.upper()


def request_message(invoice: dict, now: float):
    """Build the official seller-side fet_direct RequestPayment for ASI:One."""
    from uagents_core.contrib.protocols.payment import Funds,RequestPayment
    deadline=max(1,int(invoice['deadline_at']-now))
    metadata={"agent":"ServiceSetu","service":"service_booking","fet_network":NETWORK,
              "mainnet":"false","provider_agent_wallet":invoice['recipient'],
              "booking_id":invoice['booking_id'],"quote_id":invoice['quote_id'],
              "content":"Dorado testnet payment only; no INR conversion."}
    return RequestPayment(accepted_funds=[Funds(currency="FET",amount=invoice['token_amount'],payment_method=PAYMENT_METHOD)],
        recipient=invoice['recipient'],deadline_seconds=deadline,reference=invoice['booking_id'],
        description="ServiceSetu booking · Dorado FET TESTNET only",metadata=metadata)


def _events(tx):
    for collection in (getattr(tx, "events", {}) or {},):
        if isinstance(collection, dict):
            for kind, attrs in collection.items():
                if kind == "transfer" and isinstance(attrs, dict):
                    yield attrs
    for log in getattr(tx, "logs", ()) or ():
        for kind, attrs in (getattr(log, "events", {}) or {}).items():
            if kind == "transfer" and isinstance(attrs, dict):
                yield attrs


def _read_transfer(tx_hash: str, *, sender: str, recipient: str, amount_atomic: int, ledger=None):
    """Return verified transfer facts from Dorado's successful transaction record."""
    tx_hash = transaction_hash(tx_hash)
    if ledger is None:
        from cosmpy.aerial.client import LedgerClient, NetworkConfig
        network = NetworkConfig.fetchai_dorado_testnet()
        if network.chain_id != NETWORK:
            raise Rejected("Configured ledger is not Dorado; mainnet is refused")
        ledger = LedgerClient(network)
    tx = ledger.query_tx(tx_hash)
    if not tx or not tx.is_successful() or transaction_hash(tx.hash) != tx_hash:
        raise Rejected("Dorado transaction is missing, failed or has a mismatched hash")
    expected_amount = f"{amount_atomic}{DENOM}"
    for attrs in _events(tx):
        if (attrs.get("sender") == sender and attrs.get("recipient") == recipient
                and attrs.get("amount") == expected_amount):
            return {"sender": sender, "recipient": recipient, "amount": str(amount_atomic), "denom": DENOM}
    raise Rejected("Dorado transaction does not contain the exact expected transfer")


def verify_incoming(tx_hash: str, *, sender: str, recipient: str, amount_atomic: int, ledger=None):
    if not native_address(sender) or not native_address(recipient):
        raise Rejected("FET payments require native fetch1 wallet addresses")
    return _read_transfer(tx_hash, sender=sender, recipient=recipient, amount_atomic=amount_atomic, ledger=ledger)


def verify_refund(tx_hash: str, *, sender: str, recipient: str, amount_atomic: int, ledger=None):
    if not native_address(sender) or not native_address(recipient):
        raise Rejected("FET refunds require native fetch1 wallet addresses")
    return _read_transfer(tx_hash, sender=sender, recipient=recipient, amount_atomic=amount_atomic, ledger=ledger)


def mainnet_disabled():
    if os.getenv("FET_USE_TESTNET", "true").strip().lower() in ("0", "false", "no", "off"):
        raise Rejected("FET mainnet is disabled; only PAYMENT_MODE=fet_testnet on Dorado is supported")
    network = os.getenv("FET_NETWORK", NETWORK).strip().lower()
    if network != NETWORK:
        raise Rejected("FET payments are restricted to Dorado (dorado-1); mainnet and other networks are refused")
