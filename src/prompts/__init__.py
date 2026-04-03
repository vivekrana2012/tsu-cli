"""Built-in prompt templates for tsu-cli.

This package exists so that ``importlib.resources`` can locate the bundled
prompt files.

- ``system.md`` — control layer (output format, quality constraints) injected
  at generation time.  Never copied to ``.tsu/``; managed entirely by the package.
- ``generate.md`` — default behaviour and document-structure sections.  Copied
  into ``.tsu/generate.md`` (or ``generate-<profile>.md``) during ``tsu init``
  so users can customise the exploration strategy and output sections for each
  profile.
"""
