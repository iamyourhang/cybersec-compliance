import pytest

from scripts import ai_verify, authenticity_audit, run_full_update, verify_authoritative_links


def test_ai_verify_requires_legacy_unsafe_flag():
    with pytest.raises(SystemExit) as exc:
        ai_verify.ensure_legacy_opt_in(False)

    assert exc.value.code == 2


def test_run_full_update_requires_legacy_unsafe_flag():
    with pytest.raises(SystemExit) as exc:
        run_full_update.ensure_legacy_opt_in(False)

    assert exc.value.code == 2


def test_authenticity_audit_persist_requires_legacy_unsafe_flag():
    with pytest.raises(SystemExit) as exc:
        authenticity_audit.ensure_legacy_opt_in(False)

    assert "默认禁止" in str(exc.value)


def test_authoritative_link_verifier_requires_legacy_unsafe_flag():
    with pytest.raises(SystemExit) as exc:
        verify_authoritative_links.ensure_legacy_opt_in(False)

    assert "默认禁止" in str(exc.value)
