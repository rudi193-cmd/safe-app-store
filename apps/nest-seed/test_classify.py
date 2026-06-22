"""Tests for the date hardening in classify.py — run from inside apps/nest-seed/.

Guards the false-positive date classes found on the real ~/Desktop/Nest dump:
version strings, epoch-zero timestamps, time-of-day fragments, and out-of-range
numbers — without dropping real calendar dates.
"""
import classify as cl


def test_rejects_semver():
    for v in ("0.4.27", "4.25.19", "1.0.14", "2.10.50", "0.0.13"):
        assert cl._plausible_date(v) is False, v


def test_rejects_epoch_and_old():
    for v in ("1970-01-19", "1970-01-01", "1934/01/01"):
        assert cl._plausible_date(v) is False, v


def test_rejects_times_and_garbage():
    for v in ("22-31-25", "40-4-11", "7.3/10", "9-1.10"):
        assert cl._plausible_date(v) is False, v


def test_accepts_real_dates():
    for d in ("2026-05-31", "2025-12-17", "12/31/2024", "31.12.2024",
              "May 23, 2026", "June 6, 2026"):
        assert cl._plausible_date(d) is True, d


def test_date_fragments_filters():
    text = 'release 0.4.27 shipped on 2026-05-31; ticket 22-31-25 logged'
    refs = [f.date_ref for f in cl._date_fragments(text)]
    assert refs == ["2026-05-31"], refs


def test_min_year_guard_is_configurable(monkeypatch):
    # default floor rejects 1985; nothing real in this corpus predates ~1990
    assert cl._plausible_date("1985-06-01") is False
    assert cl._plausible_date("1995-06-01") is True


def _names(text):
    return [f.content for f in cl._titled_person_fragments(text, set())]


def test_titled_person_accepts_real_name():
    assert _names("met Mr. David Martinez today") == ["David Martinez"]
    assert _names("per Dr. Archimedes Oakenscroll") == ["Archimedes Oakenscroll"]


def test_titled_person_rejects_lowercase_trailing_word():
    # the re.IGNORECASE bug used to yield "Martinez gave" / "Seuss books" / "Savanah if"
    assert _names("Mr. Martinez gave the keys back") == []
    assert _names("Dr. Seuss books are fun") == []
    assert _names("spoke with Ms. Savanah if she calls") == []


def test_titled_person_title_case_insensitive():
    # title may be any case, name still must be Capitalized
    assert _names("mr. David Martinez") == ["David Martinez"]
