"""Unit tests for rs_common.experience (docs/02-ingestion-pipeline.md §8.3).

Pure, spaCy-free — date_spans are supplied by hand, exactly as nlpProcessing
would pass spaCy's own DATE entity offsets in production.
"""

from datetime import date

from rs_common.experience import compute_experience

TODAY = date(2026, 9, 24)


def _idx(text, substr, occurrence=1):
    """Returns the (start, end) char span of the nth occurrence of substr."""
    pos = -1
    for _ in range(occurrence):
        pos = text.index(substr, pos + 1)
    return pos, pos + len(substr)


def test_month_to_present_computed():
    text = "Experience\nAcme Corp - Backend Developer - Jan 2020 to Present\nBuilt things."
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    assert r.years == 6.7  # Jan 2020 -> Sep 2026 (today), first-of-month


def test_year_only_range_is_estimated():
    text = "Experience\nAcme - Dev - 2019 - 2021\nStuff."
    r = compute_experience(text, [], TODAY)
    assert r.basis == "estimated"
    assert r.years == 3.0  # Jan 2019 -> Dec 2021


def test_overlapping_jobs_are_merged_not_double_counted():
    text = "Experience\nJob A - Jan 2018 to Jun 2019\nJob B - Mar 2019 to Dec 2020"
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    # Merged interval: Jan 2018 -> Dec 2020, NOT (Jun2019-Jan2018)+(Dec2020-Mar2019)
    assert r.years == 2.9


def test_education_section_excluded():
    text = "Experience\nAcme - Jan 2020 to Dec 2022\n\nEducation\nState University - 2014 to 2018"
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    assert r.years == 2.9  # only the experience-section range counts


def test_numeric_month_year_format():
    text = "Experience\nAcme - 03/2018 - 06/2020"
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    assert r.years == 2.3


def test_full_month_name_sept_to_aug():
    text = "Experience\nAcme - Sept 2017 to Aug 2019"
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    assert r.years == 1.9


def test_future_start_is_dropped():
    text = "Experience\nAcme - Jan 2030 to Present"
    r = compute_experience(text, [], TODAY)
    assert r == compute_experience("Experience\nNo dates.", [], TODAY)
    assert r.years is None
    assert r.basis == "unknown"


def test_reversed_range_is_dropped():
    text = "Experience\nAcme - Jan 2022 to Jan 2020"
    r = compute_experience(text, [], TODAY)
    assert r.years is None
    assert r.basis == "unknown"


def test_no_dates_found_is_unknown():
    text = "Experience\nNo dates here at all, just prose about responsibilities."
    r = compute_experience(text, [], TODAY)
    assert r.years is None
    assert r.basis == "unknown"


def test_uncorroborated_range_outside_sections_is_ignored():
    """No header at all -> whole text is in scope, but a range only counts if
    it overlaps a spaCy DATE span (the NLP corroboration requirement)."""
    text = "Built stuff from 2019 to 2021 somewhere."
    r_no_spans = compute_experience(text, [], TODAY)
    assert r_no_spans.years is None
    assert r_no_spans.basis == "unknown"

    span_2019 = _idx(text, "2019")
    span_2021 = _idx(text, "2021")
    r_with_spans = compute_experience(text, [span_2019, span_2021], TODAY)
    assert r_with_spans.years == 3.0
    assert r_with_spans.basis == "estimated"  # no experience section -> never "computed"


def test_short_apostrophe_years():
    text = "Experience\nAcme - '19 - '21"
    r = compute_experience(text, [], TODAY)
    assert r.basis == "estimated"
    assert r.years == 3.0


def test_multiple_sections_only_experience_counts():
    text = (
        "Experience\nA - Jan 2018 to Dec 2019\n\n"
        "Projects\nSide project 2015 to 2016\n\n"
        "Education\nSchool 2010-2014"
    )
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    assert r.years == 1.9  # only Jan 2018 -> Dec 2019


def test_till_date_present_synonym():
    text = "Experience\nAcme - Jan 2020 to till date"
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    assert r.years == 6.7


def test_sixty_year_span_is_dropped():
    text = "Experience\nAcme - 1960 to 2020"
    r = compute_experience(text, [], TODAY)
    assert r.years is None
    assert r.basis == "unknown"


def test_summary_only_resume_is_unknown():
    text = "Summary\nExperienced professional with a strong track record."
    r = compute_experience(text, [], TODAY)
    assert r.years is None
    assert r.basis == "unknown"


def test_present_end_clamped_to_today_not_beyond():
    text = "Experience\nAcme - Jan 2026 to Present"
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    assert r.years == 0.7  # Jan 2026 -> Sep 2026 (today)


def test_case_insensitive_headers():
    text = "EXPERIENCE\nAcme - Jan 2020 to Dec 2021"
    r = compute_experience(text, [], TODAY)
    assert r.basis == "computed"
    assert r.years == 1.9
