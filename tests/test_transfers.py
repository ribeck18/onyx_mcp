"""Direct function-boundary tests of the pending-transfer store."""

import time

from transfers import (
    PendingTransfer,
    TRANSFER_TTL_SECONDS,
    consume_transfer,
    create_transfer,
    pending_transfers,
)


def make_transfer(kind="upload", expires_in=TRANSFER_TTL_SECONDS, **kwargs):
    return PendingTransfer(
        kind=kind,
        pat="some-pat",
        expires_at=time.time() + expires_in,
        vdi_id=1,
        filename="spec.pdf",
        **kwargs,
    )


def test_consume_is_single_use():
    token = create_transfer(make_transfer())

    first = consume_transfer(token, "upload")
    assert first is not None
    assert first.vdi_id == 1
    assert first.pat == "some-pat"

    assert consume_transfer(token, "upload") is None


def test_unknown_token_returns_none():
    assert consume_transfer("no-such-token", "upload") is None


def test_expired_token_returns_none_and_is_gone():
    token = create_transfer(make_transfer(expires_in=-1))

    assert consume_transfer(token, "upload") is None
    # pop semantics: the expired entry was removed even though consumption failed
    assert token not in pending_transfers


def test_kind_mismatch_returns_none():
    token = create_transfer(make_transfer(kind="upload"))

    assert consume_transfer(token, "download") is None


def test_create_purges_expired_entries():
    expired_token = create_transfer(make_transfer(expires_in=-1))
    assert expired_token in pending_transfers

    fresh_token = create_transfer(make_transfer())

    assert expired_token not in pending_transfers
    assert fresh_token in pending_transfers


def test_tokens_are_unique_and_unguessable_length():
    tokens = {create_transfer(make_transfer()) for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 43 for t in tokens)  # token_urlsafe(32) -> 43 chars


def test_purpose_defaults_to_submit():
    token = create_transfer(make_transfer())
    assert consume_transfer(token, "upload").purpose == "submit"
