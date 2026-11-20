"""Global pytest fixtures and runtime options.

Author: Kawhi.He
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest


@dataclass
class RunContext:
    """Container for runner metadata passed into pytest.

    Args:
        project: Normalized project key.
        case_no: Case number from runner task.
        case_name: Case name from runner task.
        base_id: Base ID from runner task.

    Returns:
        None.
    """

    project: str
    case_no: str
    case_name: str
    base_id: str


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom CLI options for pytest run metadata.

    Args:
        parser: Pytest argument parser.

    Returns:
        None.
    """
    parser.addoption("--project", action="store", default="")
    parser.addoption("--case-no", action="store", default="")
    parser.addoption("--case-name", action="store", default="")
    parser.addoption("--base-id", action="store", default="")


@pytest.fixture(scope="session", name="run_context")
def fixture_run_context(pytestconfig: pytest.Config) -> RunContext:
    """Build a session-level context object from CLI options.

    Args:
        pytestconfig: Current pytest config instance.

    Returns:
        RunContext: Session context object.
    """
    return RunContext(
        project=pytestconfig.getoption("--project"),
        case_no=pytestconfig.getoption("--case-no"),
        case_name=pytestconfig.getoption("--case-name"),
        base_id=pytestconfig.getoption("--base-id"),
    )


@pytest.fixture(scope="session", autouse=True)
def suite_lifecycle(run_context: RunContext):
    """Run suite-level init and cleanup once.

    Args:
        run_context: Session context metadata.

    Returns:
        Iterator[None]: Fixture lifecycle.
    """
    print(
        "[SUITE_INIT] project=%s case_no=%s case_name=%s base_id=%s"
        % (
            run_context.project,
            run_context.case_no,
            run_context.case_name,
            run_context.base_id,
        )
    )
    start = time.time()
    yield
    duration = time.time() - start
    print("[SUITE_CLEANUP] duration=%.3fs" % duration)


@pytest.fixture(autouse=True)
def case_lifecycle(request: pytest.FixtureRequest):
    """Run case-level setup and teardown for every test function.

    Args:
        request: Current fixture request context.

    Returns:
        Iterator[None]: Fixture lifecycle.
    """
    node_id = request.node.nodeid
    print("[CASE_INIT] %s" % node_id)
    case_start = time.time()
    yield
    cost = time.time() - case_start
    print("[CASE_CLEANUP] %s cost=%.3fs" % (node_id, cost))
