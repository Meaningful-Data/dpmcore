"""Sphinx configuration for dpmcore documentation."""

import os
import sys

# Add src/ to path so autodoc can import dpmcore.
sys.path.insert(0, os.path.abspath("../src"))

project = "dpmcore"
copyright = "2024, MeaningfulData S.L."  # noqa: A001
author = "MeaningfulData S.L."

# Pull version from the package.
from dpmcore import __version__  # noqa: E402

version = __version__
release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- HTML output -----------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# -- Napoleon (Google-style docstrings) ------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True

# -- Autodoc ---------------------------------------------------------

autodoc_member_order = "bysource"
autodoc_typehints = "description"

# -- Intersphinx -----------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
}
