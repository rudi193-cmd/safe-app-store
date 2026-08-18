"""Archived tests: not collected.

The files in this directory were moved here (not deleted — CLAUDE.md rule 4)
when the Forge engine's store-side duplicate modules were archived to
`stores/_forge_extracted/` on 2026-08-18. See the README in that directory
and in this one.

Every one of these files loads its subject module by a path relative to the
repo root (`Path(__file__).resolve().parent.parent`), computed for their
original location directly under `tests/`. Moving them one directory deeper
makes that math resolve to `tests/` instead of the repo root, so importing
them as-is raises `FileNotFoundError` at collection time rather than skipping
cleanly — and the module they load no longer exists at that path anyway,
since the module itself was archived out from under them.

Rather than patch each archived file's internal path math for tests that are
not meant to run again (the real, live versions of every one of these tests
now live in rudi193-cmd/Forge's own `tests/`), this `collect_ignore_glob`
keeps pytest from walking into this directory at all. The files stay exactly
as they were the moment they were archived — a readable historical record,
not a maintained suite.
"""
collect_ignore_glob = ["*.py"]
