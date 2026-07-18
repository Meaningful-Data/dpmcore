"""sphinx-polyversion configuration for the dpmcore documentation.

Run a full versioned build (checks out each matching git ref into an isolated
Poetry environment)::

    poetry run sphinx-polyversion docs/poly.py

Build only the current working tree using mock revision data (fast, no git
checkout -- use this to test uncommitted changes)::

    poetry run sphinx-polyversion --local docs/poly.py
"""

from datetime import datetime, timezone
from pathlib import Path

from sphinx_polyversion.api import apply_overrides
from sphinx_polyversion.driver import DefaultDriver
from sphinx_polyversion.git import (
    Git,
    GitRef,
    GitRefType,
    file_predicate,
    refs_by_type,
)
from sphinx_polyversion.pyvenv import Poetry
from sphinx_polyversion.sphinx import SphinxBuilder

#: Branches to build docs for.
BRANCH_REGEX = r"^master$"

#: Tags to build docs for. Existing tags are "0.1.1"-style (no leading "v") and
#: match nothing yet; start tagging vX.Y.Z to publish versioned docs.
TAG_REGEX = r"^v\d+\.\d+\.\d+$"

#: Output directory (relative to the project root).
OUTPUT_DIR = "_site"

#: Documentation source directory (holds conf.py).
SOURCE_DIR = "docs/"

#: Args for `poetry install` in each isolated per-version environment.
#: autodoc imports dpmcore.services.*, which pull in optional deps (pandas,
#: openpyxl, ...), so the package must be installed WITH all extras -- mirror
#: the CI install, NOT "--only docs".
POETRY_ARGS = "--all-extras --with docs"

#: Args for `sphinx-build`. -W turns warnings into errors so a broken autodoc
#: import fails the build instead of silently rendering empty API pages.
SPHINX_ARGS = "-W --keep-going"

#: Build only the working tree with mock data (overridable via --local).
MOCK = False

#: Run per-version builds in parallel.
SEQUENTIAL = False

#: Mock revision data used for --local builds of the working tree.
MOCK_DATA = {
    "revisions": [
        GitRef(
            "master",
            "",
            "",
            GitRefType.BRANCH,
            datetime.fromtimestamp(0, tz=timezone.utc),
        ),
    ],
    "current": GitRef(
        "local",
        "",
        "",
        GitRefType.BRANCH,
        datetime.fromtimestamp(0, tz=timezone.utc),
    ),
}


def data(driver, rev, env):
    """Build the Jinja context exposed to each version's templates."""
    revisions = driver.targets
    branches, tags = refs_by_type(revisions)
    return {
        "current": rev,
        "tags": tags,
        "branches": branches,
        "revisions": revisions,
        "latest": max(tags or branches),
    }


# Apply KEY=VALUE overrides passed on the command line (e.g. -o MOCK=true).
apply_overrides(globals())

root = Git.root(Path(__file__).parent)
src = Path(SOURCE_DIR)

DefaultDriver(
    root,
    OUTPUT_DIR,
    vcs=Git(
        branch_regex=BRANCH_REGEX,
        tag_regex=TAG_REGEX,
        predicate=file_predicate([src]),  # skip refs without a docs/ dir
    ),
    builder=SphinxBuilder(src, args=SPHINX_ARGS.split()),
    env=Poetry.factory(args=POETRY_ARGS.split()),
    data_factory=data,
    mock=MOCK_DATA,
).run(MOCK, SEQUENTIAL)
