from types import SimpleNamespace

from app.services.language_evidence import (
    canonical_language_credentials,
    resume_language_lines,
    verified_german_certificate,
    verified_ielts,
)


def profile(*, verified: bool = True):
    return SimpleNamespace(
        languages_json=["Spanish - Native", "English - Fluent", "German - Basic"],
        certifications_json=[
            {
                "name": "IELTS Academic",
                "language": "English",
                "score": "6.5",
                "type": "language",
                "verified": verified,
            }
        ],
        language_credentials_json=[],
    )


def test_verified_ielts_is_stored_canonically_but_general_resumes_show_proficiency():
    candidate = profile()

    assert canonical_language_credentials(candidate) == [
        {
            "language": "Spanish",
            "proficiency": "Native",
            "certificate": "",
            "score": "",
            "verified": True,
        },
        {
            "language": "English",
            "proficiency": "Fluent",
            "certificate": "IELTS Academic",
            "score": "6.5",
            "verified": True,
        },
        {
            "language": "German",
            "proficiency": "Basic",
            "certificate": "",
            "score": "",
            "verified": True,
        },
    ]
    assert resume_language_lines(candidate) == [
        "Spanish - Native",
        "English - Fluent",
        "German - Basic",
    ]
    assert resume_language_lines(candidate, show_verified_exam=True) == [
        "Spanish - Native",
        "English - IELTS Academic 6.5",
        "German - Basic",
    ]
    assert verified_ielts(candidate)["score"] == "6.5"
    assert verified_german_certificate(candidate) is None


def test_unverified_ielts_does_not_become_verified_through_fluent_language_text():
    candidate = profile(verified=False)

    assert verified_ielts(candidate) is None
    assert "English - Fluent" in resume_language_lines(candidate)
