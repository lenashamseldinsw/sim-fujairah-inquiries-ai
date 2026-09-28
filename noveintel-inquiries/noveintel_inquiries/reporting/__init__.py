"""Document assembly.

Holds the vendored ``sword_word_builder`` the report stages render with. It
is vendored rather than depended on because the service must be deployable
without the Streamlit repository it came from — the porting guide's rule that
the new service does not import from the legacy app.
"""
