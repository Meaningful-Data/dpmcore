"""Fixtures for XBRL importer integration tests.

The tests load the real (tiny) NBB SEG/FIB 2008 taxonomies that are
committed under ``tests/fixtures/xbrl/`` through Arelle, fully
offline: the only remote references they make are to the xbrl.org
core schemas, which ship inside Arelle's bundled resource cache.
"""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "xbrl"


@pytest.fixture(scope="session")
def xbrl_fixtures_dir():
    """Root of the committed XBRL taxonomy fixtures."""
    return FIXTURES_DIR


@pytest.fixture
def webcache_dir(tmp_path):
    """Throwaway Arelle web-cache directory.

    Arelle resolves the xbrl.org core schemas from its bundled
    resource cache, so an empty directory suffices for offline
    loads of the fixture taxonomies.
    """
    target = tmp_path / "webcache"
    target.mkdir()
    return target
