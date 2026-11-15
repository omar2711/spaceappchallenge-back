"""Classify existing tests without rewriting or removing their assertions."""

import pytest


def pytest_configure(config):
    for name, description in {
        "unit": "Offline unit tests with explicitly synthetic fixtures/contracts",
        "real_data": "Integration with actual downloaded FITS or recorded service results",
        "nasa_ipac": "Live small requests to NASA/IPAC (explicit opt-in env flags)",
        "pending_b1": "Real compatible B1 pair required; skip until supplied",
    }.items():
        config.addinivalue_line("markers", f"{name}: {description}")


def pytest_collection_modifyitems(items):
    for item in items:
        name = item.originalname or item.name
        if name in {"test_live_irsa_small_query", "test_live_splices_scs"}:
            marker = "nasa_ipac"
        elif name in {"test_b1_real_difference", "test_real_b1_adapter_pair"}:
            marker = "pending_b1"
        elif item.path.name in {"test_b2_real_integration.py", "test_b2_phase3_real.py", "test_b2_phase4_real.py"}:
            marker = "real_data"
        else:
            marker = "unit"
        item.add_marker(getattr(pytest.mark, marker))
