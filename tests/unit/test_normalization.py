"""Unit tests for rs_common.normalization. Requires RS_DATA_DIR pointing at
backend/data (set via pyproject.toml/Makefile for the whole test run)."""

from rs_common import normalization as norm


def test_normalize_skill_synonym():
    assert norm.normalize_skill("JS") == "javascript"
    assert norm.normalize_skill(" k8s ") == "kubernetes"
    assert norm.normalize_skill("Postgres") == "postgresql"


def test_normalize_skill_passthrough_when_no_synonym():
    assert norm.normalize_skill("Python") == "python"
    assert norm.normalize_skill("  AWS  ") == "aws"


def test_normalize_title_synonym():
    assert norm.normalize_title("SWE") == "software engineer"
    assert norm.normalize_title("sde") == "software engineer"


def test_normalize_list_dedupes_sorts_drops_falsy():
    assert norm.normalize_list(["b", "a", "a", "", None, "c"]) == ["a", "b", "c"]


def test_skill_patterns_include_synonym_keys_not_case_sensitive_canonicals():
    patterns = set(norm.skill_patterns())
    assert "k8s" in patterns  # synonym key, matchable so normalization actually triggers
    assert "javascript" in patterns  # real dictionary entry
    assert "go" not in patterns  # case-sensitive canonical, excluded from case-insensitive matcher


def test_case_sensitive_skills_content():
    cs = norm.case_sensitive_skills()
    assert cs.get("Go") == "go"
    assert cs.get("R") == "r"
    assert cs.get("C") == "c"


def test_title_patterns_include_dictionary_and_synonyms():
    patterns = set(norm.title_patterns())
    assert "backend engineer" in patterns
    assert "sde" in patterns


def test_extract_email_found():
    text = "Contact: jane.doe@example-mail.test for details."
    assert norm.extract_email(text) == "jane.doe@example-mail.test"


def test_extract_email_none_when_absent():
    assert norm.extract_email("No contact info here.") is None


def test_extract_email_lowercased():
    assert norm.extract_email("EMAIL: John.Doe@Example.COM") == "john.doe@example.com"


def test_extract_min_years_simple():
    assert norm.extract_min_years("Requires 3+ years of experience.") == 3


def test_extract_min_years_picks_smallest_plausible():
    assert norm.extract_min_years("2-4 years preferred, ideally 5+ years.") == 2


def test_extract_min_years_none_when_absent():
    assert norm.extract_min_years("No experience requirement mentioned.") is None


def test_extract_min_years_ignores_implausible_values():
    # A bare "years" mention with no sane number nearby shouldn't produce junk.
    assert norm.extract_min_years("Founded in 1999, still going strong.") is None
