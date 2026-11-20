"""LINKE demo test cases for runner integration.

Author: Kawhi.He
"""

from __future__ import annotations

import time


def test_linke_connection_smoke(run_context):
    """Verify LINKE connection smoke flow.

    Args:
        run_context: Session metadata fixture from pytest.

    Returns:
        None.
    """
    print("[LINKE] start connection smoke check")
    print(
        "[LINKE] context project=%s case_no=%s"
        % (run_context.project, run_context.case_no)
    )
    time.sleep(0.2)
    assert run_context.project == "linke"


def test_linke_data_process_smoke(run_context):
    """Verify LINKE data processing smoke flow.

    Args:
        run_context: Session metadata fixture from pytest.

    Returns:
        None.
    """
    print("[LINKE] start data process smoke check")
    time.sleep(0.2)
    # Demo assertion for proving pass/fail propagation.
    assert "LKE" in (run_context.case_no or "LKE-DEFAULT")


def test_linke_fail_demo_for_callback(run_context):
    """Simulate a deterministic failure for callback verification.

    Args:
        run_context: Session metadata fixture from pytest.

    Returns:
        None.
    """
    print("[LINKE] start fail-demo callback check")
    print(
        "[LINKE] fail-demo context case_no=%s base_id=%s"
        % (run_context.case_no, run_context.base_id)
    )
    time.sleep(0.2)
    # Keep this assertion always false so the platform can verify FAIL write-back.
    assert False, "Intentional failure demo for callback validation"
