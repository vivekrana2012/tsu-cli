"""Built-in prompt templates for tsu-cli.

This package exists so that ``importlib.resources`` can locate the bundled
generate.md template.  The template is copied into ``.tsu/generate.md``
during ``tsu init`` and read directly from there at generation time.
"""
