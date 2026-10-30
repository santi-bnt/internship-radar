"""Canonical language evidence shared by every resume target."""

from __future__ import annotations

import re
from typing import Any, Iterable


OFFICIAL_GERMAN_EXAMS = (
    "goethe",
    "testdaf",
    "telc",
    "osd",
    "ösd",
    "österreichisches sprachdiplom",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _language_name(value: Any) -> str:
    return re.split(r"\s+(?:—|-)\s+", _clean(value), maxsplit=1)[0].strip()


def _language_detail(value: Any) -> str:
    parts = re.split(r"\s+(?:—|-)\s+", _clean(value), maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


def _credential(
    *,
    language: Any,
    proficiency: Any = "",
    certificate: Any = "",
    score: Any = "",
    verified: Any = False,
) -> dict[str, Any] | None:
    name = _clean(language)
    if not name:
        return None
    return {
        "language": name,
        "proficiency": _clean(proficiency),
        "certificate": _clean(certificate),
        "score": _clean(score),
        "verified": verified is True,
    }


def _certification_language(item: dict[str, Any]) -> str:
    explicit = _clean(item.get("language"))
    if explicit:
        return explicit
    text = " ".join(_clean(value) for value in item.values()).casefold()
    if "ielts" in text:
        return "English"
    if "german" in text or any(exam in text for exam in OFFICIAL_GERMAN_EXAMS):
        return "German"
    return ""


def _is_language_certification(item: dict[str, Any]) -> bool:
    text = " ".join(_clean(value) for value in item.values()).casefold()
    return (
        _clean(item.get("type")).casefold() == "language"
        or bool(_clean(item.get("language")))
        or "ielts" in text
        or any(exam in text for exam in OFFICIAL_GERMAN_EXAMS)
    )


def canonical_language_credentials(profile: Any) -> list[dict[str, Any]]:
    """Merge structured credentials, legacy certifications, and profile languages.

    Structured credentials are canonical. Legacy fields remain readable so an
    existing verified certificate is never lost during rollout.
    """

    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def merge(candidate: dict[str, Any] | None) -> None:
        if not candidate:
            return
        key = candidate["language"].casefold()
        if key not in merged:
            merged[key] = candidate
            order.append(key)
            return
        current = merged[key]
        if candidate["proficiency"]:
            current["proficiency"] = candidate["proficiency"]
        if candidate["certificate"]:
            current["certificate"] = candidate["certificate"]
            current["score"] = candidate["score"]
            # Certificate verification is independent from a self-reported
            # language level such as "English - Fluent".
            current["verified"] = candidate["verified"]
        elif not current["certificate"]:
            current["verified"] = bool(current["verified"] or candidate["verified"])

    for item in getattr(profile, "languages_json", []) or []:
        language = _language_name(item)
        detail = _language_detail(item)
        merge(
            _credential(
                language=language,
                proficiency=detail,
                verified=bool(language and detail),
            )
        )

    for item in getattr(profile, "certifications_json", []) or []:
        if not isinstance(item, dict) or not _is_language_certification(item):
            continue
        merge(
            _credential(
                language=_certification_language(item),
                proficiency=item.get("proficiency", item.get("level", "")),
                certificate=item.get("name", item.get("title", "")),
                score=item.get("score", item.get("result", "")),
                verified=item.get("verified", False),
            )
        )

    # The structured profile field is authoritative and therefore merges last.
    for item in getattr(profile, "language_credentials_json", []) or []:
        if not isinstance(item, dict):
            continue
        merge(
            _credential(
                language=item.get("language"),
                proficiency=item.get("proficiency", item.get("level", "")),
                certificate=item.get("certificate", item.get("exam", "")),
                score=item.get("score", item.get("result", "")),
                verified=item.get("verified", False),
            )
        )

    return [merged[key] for key in order]


def language_certifications(
    credentials: Iterable[dict[str, Any]],
    certifications: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Synchronize canonical language credentials back to legacy certificates."""

    result = [
        dict(item)
        for item in certifications
        if isinstance(item, dict) and not _is_language_certification(item)
    ]
    for item in credentials:
        certificate = _clean(item.get("certificate"))
        if not certificate:
            continue
        result.append(
            {
                "name": certificate,
                "score": _clean(item.get("score")),
                "language": _clean(item.get("language")),
                "type": "language",
                "verified": item.get("verified") is True,
            }
        )
    return result


def verified_ielts(profile: Any) -> dict[str, Any] | None:
    for item in canonical_language_credentials(profile):
        certificate = item["certificate"].casefold()
        if (
            item["language"].casefold() == "english"
            and item["verified"] is True
            and "ielts" in certificate
            and "academic" in certificate
            and item["score"]
        ):
            return item
    return None


def verified_german_certificate(profile: Any) -> dict[str, Any] | None:
    for item in canonical_language_credentials(profile):
        certificate = item["certificate"].casefold()
        if (
            item["language"].casefold() == "german"
            and item["verified"] is True
            and any(exam in certificate for exam in OFFICIAL_GERMAN_EXAMS)
            and (item["score"] or item["proficiency"])
        ):
            return item
    return None


def resume_language_lines(profile: Any, *, show_verified_exam: bool = False) -> list[str]:
    """Return language lines for ordinary CVs without discarding credentials.

    A candidate's current proficiency is the useful default on general resumes.
    Program-specific resumes may opt into official-exam wording while still using
    the same structured, verified credential record.
    """

    result: list[str] = []
    for item in canonical_language_credentials(profile):
        if show_verified_exam and item["certificate"] and item["verified"]:
            detail = " ".join(part for part in (item["certificate"], item["score"]) if part)
        else:
            detail = item["proficiency"] or (
                " ".join(part for part in (item["certificate"], item["score"]) if part)
                if item["certificate"] and item["verified"] else ""
            )
        if detail:
            result.append(f"{item['language']} - {detail}")
    return result
