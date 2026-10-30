from copy import deepcopy

from app.services.scoring import analyze_job
from app.services.scoring import _skill_matches


def test_java_is_not_inferred_from_verified_c_cpp_python():
    job = {"title": "Software Intern", "description": "Java C++ Python",
           "requirements": "Required: Java, C++, Python", "preferred_qualifications": ""}
    candidate = {"skills_json": ["C", "C++", "Python"]}
    matched, missing, _, _ = _skill_matches(job, candidate)
    assert "java" not in matched
    assert "java" in missing
    assert "c++" in matched and "python" in matched


def test_citizenship_requirement_is_not_eligible(profile, base_job):
    job = deepcopy(base_job)
    job["country"] = "United States"
    job["location"] = "Arlington, Virginia, United States"
    job["requirements"] += " Must be a U.S. citizen."
    result = analyze_job(job, profile)
    assert result.recommendation == "Not Eligible"
    assert any("citizenship" in reason.lower() for reason in result.blocker_reasons)


def test_explicit_no_sponsorship_is_not_eligible(profile, base_job):
    job = deepcopy(base_job)
    job["country"] = "United States"
    job["location"] = "Austin, Texas, United States"
    job["requirements"] += " The company will not sponsor employment visas."
    assert analyze_job(job, profile).recommendation == "Not Eligible"


def test_missing_sponsorship_information_is_review_not_rejection(profile, base_job):
    job = deepcopy(base_job)
    job["country"] = "United States"
    job["location"] = "Austin, Texas, United States"
    result = analyze_job(job, profile)
    assert result.recommendation == "Review"
    assert result.blocker_reasons == []
    assert any("sponsorship" in flag.lower() for flag in result.risk_flags)


def test_sde_match_scores_well(profile, base_job):
    job = deepcopy(base_job)
    job.update(
        {
            "title": "Software Development Engineer Intern",
            "description": "Build backend services in Java and Python on Linux.",
            "requirements": "Required: Java or Python, Git, data structures, and testing.",
            "preferred_qualifications": "Preferred: SQL and cloud experience.",
        }
    )
    result = analyze_job(job, profile)
    assert result.technical_score >= 55
    assert result.recommended_resume_type == "Software / SDE"


def test_fpga_match_scores_well(profile, base_job):
    job = deepcopy(base_job)
    job.update(
        {
            "title": "FPGA RTL Intern",
            "description": "Implement digital logic and FPGA prototypes.",
            "requirements": "Required: Verilog, RTL, FPGA, digital design, and Linux.",
            "preferred_qualifications": "Preferred: Python and hardware testing.",
        }
    )
    result = analyze_job(job, profile)
    assert result.technical_score >= 70
    assert result.recommended_resume_type == "FPGA / RTL / Digital Design"


def test_senior_role_receives_level_penalty(profile, base_job):
    job = deepcopy(base_job)
    job["title"] = "Senior Firmware Engineer"
    job["employment_type"] = "Full-time"
    result = analyze_job(job, profile)
    assert result.level_score <= 20
    assert result.recommendation == "Low Match"


def test_preferred_gap_weighs_less_than_required_gap(profile, base_job):
    required_gap = deepcopy(base_job)
    required_gap["requirements"] += " Required: SQL."
    preferred_gap = deepcopy(base_job)
    preferred_gap["preferred_qualifications"] += " Preferred: SQL."
    assert analyze_job(preferred_gap, profile).technical_score > analyze_job(required_gap, profile).technical_score


def test_closed_job_never_becomes_apply_today(profile, base_job):
    job = deepcopy(base_job)
    job["is_active"] = False
    assert analyze_job(job, profile).recommendation == "Closed"


def test_score_contains_explanations(profile, base_job):
    result = analyze_job(base_job, profile)
    assert result.explanation
    assert result.positive_reasons
    assert "45/20/15/10/5/5" in result.explanation
