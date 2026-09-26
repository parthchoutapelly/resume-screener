# NLP Quality Evaluation

> Generated 2026-09-26 03:39 UTC — env `dev` — **do not edit by hand** (re-run `make evaluate`)

## Summary

| Metric | Result | Target (SC3) | Pass |
|--------|--------|-------------|------|
| Skill precision | 0.910 | ≥ 0.80 | ✅ |
| Skill recall | 1.000 | ≥ 0.70 | ✅ |
| Name accuracy | 10/10 (100%) | ≥ 8/10 | ✅ |
| Experience accuracy (±1 yr) | 9/9 (100%) | ≥ 7/9 | ✅ |
| Title hit rate | 10/10 (100%) | report only | — |

Evaluated against 10 scorable fixture(s).

## Per-fixture results

| Fixture | TP | FP | FN | Name | Exp | Title |
|---|---|---|---|---|---|---|
| alice_johnson_native.pdf | 10 | 3 | 0 | ✅ | ✅ | ✅ |
| bob_kumar.docx | 6 | 0 | 0 | ✅ | ✅ | ✅ |
| carol_singh.docx | 5 | 0 | 0 | ✅ | ✅ | ✅ |
| daniel_kim_scanned.pdf | 4 | 0 | 0 | ✅ | ✅ | ✅ |
| jordan_rivera.png | 4 | 0 | 0 | ✅ | ✅ | ✅ |
| maya_bennett_mixed.pdf | 4 | 0 | 0 | ✅ | ✅ | ✅ |
| lena_kowalski.docx | 11 | 1 | 0 | ✅ | ✅ | ✅ |
| omar_hassan_scanned.pdf | 12 | 0 | 0 | ✅ | ✅ | ✅ |
| priya_sharma_native.pdf | 11 | 3 | 0 | ✅ | ✅ | ✅ |
| worked_example_native.pdf | 4 | 0 | 0 | ✅ | ✅ | ✅ |

## Misses and causes

| Fixture | Type | Value | Expected | Got | Cause |
|---|---|---|---|---|---|
| alice_johnson_native.pdf | skill_fp | cd |  |  | ner_miss_or_dict_gap |
| alice_johnson_native.pdf | skill_fp | ci |  |  | ner_miss_or_dict_gap |
| alice_johnson_native.pdf | skill_fp | github |  |  | ner_miss_or_dict_gap |
| lena_kowalski.docx | skill_fp | apache |  |  | ner_miss_or_dict_gap |
| priya_sharma_native.pdf | skill_fp | cd |  |  | ner_miss_or_dict_gap |
| priya_sharma_native.pdf | skill_fp | ci |  |  | ner_miss_or_dict_gap |
| priya_sharma_native.pdf | skill_fp | github |  |  | ner_miss_or_dict_gap |

## Miss classification legend

| Code | Meaning |
|------|---------|
| `dictionary_gap` | Term is in the truth but absent from `backend/data/skills_dictionary.json` or `job_titles_dictionary.json` |
| `ocr_noise` | Fixture is a scanned/image file; likely OCR rendering artefact |
| `ner_miss` | Term is in the dictionary but spaCy NER/PhraseMatcher did not detect the span |
| `section_detection` | Experience section header not recognised; date ranges ignored |

## Overall

**PASS**
