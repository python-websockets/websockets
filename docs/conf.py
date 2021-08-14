# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import datetime
import os
import sys

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.join(os.path.abspath(".."), "src"))


# -- Project information -----------------------------------------------------

project = "websockets"
copyright = f"2013-{datetime.date.today().year}, Aymeric Augustin and contributors"
author = "Aymeric Augustin"

# The full version, including alpha/beta/rc tags
release = "9.1"


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
    "sphinx_inline_tabs",
    "sphinxcontrib.spelling",
    "sphinxcontrib_trio",
    "sphinxext.opengraph",
]

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

spelling_show_suggestions = True

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "furo"

html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#306998",  # blue from logo
        "color-brand-content": "#0b487a",  # blue more saturated and less dark
    },
    "dark_css_variables": {
        "color-brand-primary": "#ffd43bcc",  # yellow from logo, more muted than content
        "color-brand-content": "#ffd43bd9",  # yellow from logo, transparent like text
    },
    "sidebar_hide_name": True,
}

html_logo = "_static/websockets.svg"

html_favicon = "_static/favicon.ico"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

html_copy_source = False

html_show_sphinx = False
