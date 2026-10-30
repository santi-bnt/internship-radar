from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.services.kospie import (
    DEFAULT_INTERESTS,
    DEFAULT_UNIVERSITIES,
    analyze_kospie_profile,
    build_kospie_job,
    generate_kospie_content,
    rank_kospie_projects,
    score_kospie_project,
)
from app.services.resume_generation import (
    classify_job,
    fit_kospie_resume_to_two_pages,
    generate_local_content,
    render_latex,
    resume_filename,
)
from app.services.seed import INTERNSHIP_RADAR_PROJECT, VERIFIED_COURSES, VERIFIED_RESUME_PROJECTS
from conftest import security_headers


def candidate() -> SimpleNamespace:
    projects = deepcopy(VERIFIED_RESUME_PROJECTS) + [deepcopy(INTERNSHIP_RADAR_PROJECT)]
    skills = sorted({technology for project in projects for technology in project.get("technologies", [])})
    return SimpleNamespace(
        full_name="Alex Rivera", email="candidate@example.com",
        phone="+52 55 0000 0000", location="Zapopan, Jalisco, Mexico",
        linkedin_url="https://www.linkedin.com/in/example-candidate/", github_url="https://github.com/candidate",
        headline="Robotics and Digital Systems Engineering Student", summary="Verified profile.",
        education_json=[{
            "institution": "Tecnologico de Monterrey", "degree": "B.S. in Robotics and Digital Systems Engineering",
            "location": "Zapopan, Jalisco, Mexico", "graduation": "Expected Graduation: June 2028",
            "gpa": "93.05/100", "coursework": ["Control Systems", "Signals and Systems", "Digital Systems"],
        }],
        skills_json=skills, experience_json=[], projects_json=projects,
        coursework_json=deepcopy(VERIFIED_COURSES) + [
            {"name": "Embedded Systems", "institution": "Tecnologico de Monterrey", "areas": ["Embedded Systems", "Microcontrollers"]},
            {"name": "Computer Architecture", "institution": "Tecnologico de Monterrey", "areas": ["Computer Architecture", "Digital Systems"]},
            {"name": "Electronics", "institution": "Tecnologico de Monterrey", "areas": ["Electronics"]},
        ],
        certifications_json=[{"name": "IELTS Academic", "score": "6.5", "language": "English", "type": "language", "verified": True}],
        languages_json=["Spanish - Native", "English - Fluent", "German - Basic"],
        forbidden_claims_json=["ROS 2", "SLAM", "CUDA", "Gazebo", "Machine Learning"],
    )


def configuration(universities: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        selected_universities_json=universities or list(DEFAULT_UNIVERSITIES),
        primary_interests_json=list(DEFAULT_INTERESTS),
    )


def user_profile() -> SimpleNamespace:
    return SimpleNamespace(
        citizenship_country="Mexico", citizenship_status="CONFIRMED",
        willing_to_relocate=True,
    )


def test_kospie_prioritizes_engineering_and_uses_only_verified_facts():
    profile = candidate()
    job = build_kospie_job(configuration(), profile, user_profile())
    content = generate_kospie_content(job, profile)
    names = [item.name for item in content.projects]
    assert names[:2] == [
        "MATT Web-Controlled Writing Robot",
        "Intel MAX 10 Robotic Arm Controller",
    ]
    assert "DC Motor Position Control System with WebXR Interface" in names
    assert 4 <= len(content.projects) <= 5
    assert content.headline == (
        "Robotics and Digital Systems Engineering Student | "
        "Embedded Systems | Robotics | Software"
    )
    assert [group.model_dump() for group in content.skill_categories] == [
        {
            "name": "Embedded Systems",
            "items": [
                "FreeRTOS", "Microcontrollers", "Robotics",
                "Hardware/Software Integration",
            ],
        },
        {
            "name": "Programming",
                "items": ["Python", "C", "C++", "Verilog"],
        },
        {
            "name": "Digital Systems & Hardware",
            "items": ["FPGA", "Intel MAX 10", "UART", "PWM"],
        },
    ]
    assert [item.name for item in content.coursework] == [
        "Python Data Structures",
        "Using Python to Access Web Data",
        "Programming for Everybody (Getting Started with Python)",
    ]
    assert "English - IELTS Academic 6.5" in content.languages
    assert "Spanish - Native" in content.languages
    assert "German - Basic proficiency" in content.languages
    assert all("German - A2" not in language for language in content.languages)
    assert all(skill not in content.selected_skills for skill in ("ROS 2", "SLAM", "CUDA", "Gazebo", "Machine Learning"))
    assert content.section_order == [
        "education", "skills", "projects", "languages",
        "additional_information", "coursework",
    ]


def test_kospie_courses_and_university_context_never_create_candidate_facts():
    profile = candidate()
    analysis = analyze_kospie_profile(profile, user_profile(), configuration())
    selected_courses = {
        item["name"] for group in analysis["recommended_coursework"].values() for item in group
    }
    verified_courses = {
        item if isinstance(item, str) else item["name"] for item in profile.coursework_json
    } | set(profile.education_json[0]["coursework"])
    assert selected_courses <= verified_courses
    assert "Autonomous Systems" not in analysis["recommended_skills"]
    robotics = {"name": "Robot", "technologies": ["C"], "bullets": ["robot control"]}
    generic = {"name": "App", "technologies": ["C"], "bullets": ["software"]}
    robotics_score = score_kospie_project(robotics, ["Robotics", "Control"])
    assert robotics_score > score_kospie_project(robotics, [])
    assert robotics_score > score_kospie_project(generic, ["Robotics", "Control"])


def test_strong_software_can_outrank_small_embedded_project():
    strong_software = deepcopy(INTERNSHIP_RADAR_PROJECT)
    small_embedded = {
        "name": "Small Embedded Exercise",
        "technologies": ["C", "GPIO"],
        "bullets": [
            "Built an embedded LED exercise.",
            "Tested one GPIO output.",
        ],
    }
    context = ["Robotics", "Embedded Systems", "Control"]
    assert score_kospie_project(strong_software, context) > score_kospie_project(
        small_embedded,
        context,
    )


def test_keyword_stuffed_lab_cannot_outrank_evidenced_complete_system():
    keyword_stuffed_lab = {
        "name": "ESP32 Control Laboratory Practice",
        "project_type": "laboratory practice",
        "technologies": [
            "ESP32", "PWM", "Interrupts", "Control Systems", "Sensors",
            "Actuators", "UART", "I2C", "FreeRTOS",
        ],
        "bullets": [
            "Implemented PWM and interrupts for one classroom motor exercise.",
            "Tested one sensor reading over UART during the laboratory practice.",
        ],
    }
    complete_system = next(
        item
        for item in candidate().projects_json
        if item["name"] == "SkiliAir Air Quality Monitoring System"
    )
    context = ["Robotics", "Embedded Systems", "Control"]

    lab_assessment = next(
        item
        for item in rank_kospie_projects(
            SimpleNamespace(projects_json=[keyword_stuffed_lab]), context, limit=1
        )
    )
    assert lab_assessment["project_type"] == "laboratory_practice"
    assert score_kospie_project(complete_system, context) > lab_assessment["score"]
    assert lab_assessment["components"]["classroom_exercise_penalty"] > 0


def test_portfolio_can_reject_a_higher_scoring_duplicate_for_distinct_value():
    profile = candidate()
    duplicate_robot = deepcopy(profile.projects_json[0])
    duplicate_robot["name"] = "Second Web-Controlled Writing Robot"
    profile.projects_json.append(duplicate_robot)

    ranking = rank_kospie_projects(
        profile,
        ["Robotics", "Embedded Systems", "Control", "Digital Systems"],
    )
    duplicate = next(item for item in ranking if item["name"] == duplicate_robot["name"])
    freertos = next(item for item in ranking if item["name"] == "FreeRTOS Event-Driven System")

    assert duplicate["score"] > freertos["score"]
    assert duplicate["selected"] is False
    assert any(
        item["selected"]
        for item in rank_kospie_projects(
            profile,
            ["Robotics", "Embedded Systems", "Control", "Digital Systems"],
        )
        if item["name"] in {
            "FreeRTOS Event-Driven System",
            "DC Motor Position Control System with WebXR Interface",
        }
    )


def test_generic_crud_remains_low_priority_and_radar_is_not_generic():
    generic_crud = {
        "name": "Generic Web CRUD",
        "technologies": ["React"],
        "bullets": [
            "Built a simple CRUD tutorial.",
            "Created a basic React landing page.",
        ],
    }
    generic_score = score_kospie_project(generic_crud, [])
    radar_assessment = next(
        item
        for item in rank_kospie_projects(candidate(), [], limit=5)
        if item["name"] == INTERNSHIP_RADAR_PROJECT["name"]
    )
    assert generic_score < 30
    assert radar_assessment["score"] > generic_score
    assert radar_assessment["components"]["generic_penalty"] == 0
    assert "Software Engineering" in radar_assessment["domains"]


def test_kospie_selection_combines_distinct_engineering_domains():
    ranking = rank_kospie_projects(
        candidate(),
        ["Robotics", "Embedded Systems", "Control", "Digital Systems"],
    )
    selected = [item for item in ranking if item["selected"]]
    covered = {domain for item in selected for domain in item["domains"]}
    assert 4 <= len(selected) <= 5
    assert {
        "Robotics",
        "Embedded Systems",
        "FPGA / Digital Systems",
        "Software Engineering",
        "Control Systems",
    } <= covered


def test_radar_resume_content_uses_only_stored_features_and_technologies():
    profile = candidate()
    content = generate_kospie_content(
        build_kospie_job(configuration(), profile, user_profile()),
        profile,
    )
    rendered = next(item for item in content.projects if item.name == INTERNSHIP_RADAR_PROJECT["name"])
    source = next(item for item in profile.projects_json if item["name"] == rendered.name)
    assert rendered.bullets == source["bullets"]
    assert set(rendered.technologies) <= set(source["technologies"])
    assert set(rendered.technologies) <= set(profile.skills_json)


def test_motor_project_is_p_control_and_distinct_from_discrete_pid_project():
    profile = candidate()
    motor = next(
        item
        for item in profile.projects_json
        if item["name"] == "DC Motor Position Control System with WebXR Interface"
    )
    pid = next(
        item
        for item in profile.projects_json
        if item["name"] == "ESP32 Discrete PID Controller with Analog Reference"
    )
    motor_assessment = next(
        item for item in rank_kospie_projects(profile, ["Robotics", "Embedded Systems", "Control"])
        if item["name"] == motor["name"]
    )
    motor_claims = " ".join(motor["bullets"]).casefold()

    assert motor["source_path"] != pid["source_path"]
    assert motor["technical_details"]["controller"] == "proportional (P), not PID"
    assert "proportional control" in motor_claims
    assert "pid" not in motor_claims
    assert motor_assessment["project_type"] == "complete_project"
    assert motor_assessment["components"]["classroom_exercise_penalty"] == 0
    assert pid["technical_details"]["controller_gains"] == {"Kp": 4.5122, "Ki": 21.002, "Kd": 0.1834}


def test_every_project_has_evidence_based_selection_explanation():
    ranking = rank_kospie_projects(
        candidate(),
        ["Robotics", "Embedded Systems", "Control", "Digital Systems"],
    )

    for item in ranking:
        explanation = " ".join(item["reasons"])
        assert explanation.startswith("Selected because") or explanation.startswith("Rejected because")
        assert "Technical strength:" in explanation
        assert "Scope:" in explanation
        assert "Integration:" in explanation
        assert "Unique value:" in explanation


def test_selected_universities_can_change_order_but_never_project_facts():
    automation = {
        "name": "Automation Systems Project",
        "technologies": ["Python", "Software Engineering"],
        "bullets": [
            "Implemented modular automation and validation workflows.",
            "Tested maintainable software components in a practical system.",
        ],
    }
    architecture = {
        "name": "Computer Architecture Project",
        "technologies": ["Python", "Software Engineering"],
        "bullets": [
            "Implemented modular computer architecture validation workflows.",
            "Tested maintainable software components in a practical system.",
        ],
    }
    profile = candidate()
    profile.projects_json = [deepcopy(automation), deepcopy(architecture)]
    original = deepcopy(profile.projects_json)

    kit = rank_kospie_projects(profile, ["Automation"])
    ulm = rank_kospie_projects(profile, ["Computer Architecture"])

    assert kit[0]["name"] == automation["name"]
    assert ulm[0]["name"] == architecture["name"]
    assert profile.projects_json == original


def test_kospie_language_eligibility_and_rendering_are_separate():
    profile = candidate()
    analysis = analyze_kospie_profile(profile, user_profile(), configuration())
    eligibility = {item["requirement"]: item["status"] for item in analysis["eligibility"]}
    assert eligibility["English certificate"] == "MET"
    assert eligibility["German certificate (A2 minimum)"] == "NOT YET VERIFIED"
    content = generate_kospie_content(build_kospie_job(configuration(), profile, user_profile()), profile)
    latex = render_latex(content, profile)
    assert "IELTS Academic 6.5" in latex
    assert "German - Basic proficiency" in latex
    assert "German - A2" not in latex


def test_verified_basic_german_never_satisfies_official_a2_requirement():
    profile = candidate()
    profile.language_credentials_json = [
        {"language": "Spanish", "proficiency": "Native", "verified": True},
        {
            "language": "English", "proficiency": "Fluent",
            "certificate": "IELTS Academic", "score": "6.5", "verified": True,
        },
        {"language": "German", "proficiency": "Basic", "verified": True},
    ]

    analysis = analyze_kospie_profile(profile, user_profile(), configuration())
    german = next(
        item for item in analysis["language_status"] if item["language"] == "German"
    )
    eligibility = next(
        item
        for item in analysis["eligibility"]
        if item["requirement"] == "German certificate (A2 minimum)"
    )
    content = generate_kospie_content(
        build_kospie_job(configuration(), profile, user_profile()),
        profile,
    )

    assert german["status"] == "PROFILE VERIFIED"
    assert german["evidence"] == "Basic (self-reported current proficiency)"
    assert german["requirement"] == "NOT YET VERIFIED"
    assert eligibility["status"] == "NOT YET VERIFIED"
    assert eligibility["evidence"] == (
        "Current profile level: Basic; no official A2 certificate verified."
    )
    assert content.languages == [
        "Spanish - Native",
        "English - IELTS Academic 6.5",
        "German - Basic proficiency",
    ]
    assert all("German - A2" not in language for language in content.languages)


def test_certification_only_ielts_reaches_kospie_cv_eligibility_and_latex():
    profile = candidate()
    profile.languages_json = ["Spanish - Native", "German - Basic"]
    profile.language_credentials_json = []

    analysis = analyze_kospie_profile(profile, user_profile(), configuration())
    content = generate_kospie_content(
        build_kospie_job(configuration(), profile, user_profile()),
        profile,
    )
    english = next(
        item for item in analysis["language_status"] if item["language"] == "English"
    )
    eligibility = next(
        item for item in analysis["eligibility"] if item["requirement"] == "English certificate"
    )
    latex = render_latex(content, profile)

    assert english == {
        "language": "English",
        "status": "VERIFIED",
        "exam": "IELTS Academic",
        "score": "6.5",
        "minimum": "6.0",
        "requirement": "MET",
    }
    assert eligibility["status"] == "MET"
    assert eligibility["evidence"] == "IELTS Academic 6.5"
    assert content.languages == [
        "Spanish - Native", "English - IELTS Academic 6.5",
        "German - Basic proficiency",
    ]
    assert r"\sectionheading{Languages}" in latex
    assert r"\sectionheading{Courses}" in latex
    assert r"\sectionheading{Relevant Coursework}" not in latex
    assert latex.index(r"\sectionheading{Languages}") < latex.index(
        r"\sectionheading{Additional Information}"
    ) < latex.index(r"\sectionheading{Courses}")
    assert "English - IELTS Academic 6.5" in latex
    assert "German - Basic proficiency" in latex
    assert "German - A2" not in latex
    assert all(university not in latex for university in DEFAULT_UNIVERSITIES)
    assert "93.05/100" in latex
    assert "4.0" not in latex


def test_kospie_accepts_natural_one_or_two_page_output_without_expansion(monkeypatch):
    profile = candidate()
    job = build_kospie_job(configuration(), profile, user_profile())
    content = generate_kospie_content(job, profile)
    calls = []

    def fake_compile(source: str):
        calls.append(source)
        return b"%PDF", 1, 72.0

    monkeypatch.setattr("app.services.resume_generation._compile_latex_artifact", fake_compile)
    fitted, _, _, usage = fit_kospie_resume_to_two_pages(content, job, profile)
    assert usage == 72.0
    assert fitted.quality_checks.one_page is True
    assert fitted.quality_checks.within_two_pages is True
    assert len(calls) == 1

    monkeypatch.setattr("app.services.resume_generation._compile_latex_artifact", lambda source: (b"%PDF", 2, 100.0))
    fitted, _, _, _ = fit_kospie_resume_to_two_pages(content, job, profile)
    assert fitted.quality_checks.one_page is False
    assert fitted.quality_checks.within_two_pages is True


def test_kospie_compacts_a_sparse_second_page_before_accepting_it(monkeypatch):
    profile = candidate()
    job = build_kospie_job(configuration(), profile, user_profile())
    content = generate_kospie_content(job, profile)
    original_projects = [item.name for item in content.projects]
    calls = []

    def fake_compile(source: str):
        calls.append(source)
        return (b"%PDF", 2, 100.0) if len(calls) == 1 else (b"%PDF", 1, 92.0)

    monkeypatch.setattr("app.services.resume_generation._compile_latex_artifact", fake_compile)
    monkeypatch.setattr("app.services.resume_generation._has_sparse_second_page", lambda _: True)
    fitted, _, _, _ = fit_kospie_resume_to_two_pages(content, job, profile)

    assert len(calls) == 2
    assert fitted.quality_checks.one_page is True
    assert [item.name for item in fitted.projects] == original_projects


def test_existing_resume_targets_and_filename_remain_distinct():
    profile = candidate()
    software = SimpleNamespace(
        title="Software Engineering Intern", company="Example", area="Software",
        description="C++ Python software", requirements="C++", preferred_qualifications="Python",
        resume_target="software_engineering", application_type="STANDARD_JOB", analysis=None,
    )
    research = SimpleNamespace(**{**software.__dict__, "resume_target": "robotics_research", "application_type": "STANDARD_JOB"})
    assert classify_job(software) == "Software Engineering"
    assert classify_job(research) == "Robotics Research"
    assert len(generate_local_content(software, profile).projects) <= 4
    assert len(generate_local_content(research, profile).projects) <= 4
    assert resume_filename("Alex Rivera", "Anything", "kospie_germany") == "Alex_Rivera_KOSPIE_DAAD_CV.pdf"


def test_kospie_scoring_is_not_called_by_existing_resume_targets(monkeypatch):
    profile = candidate()
    software = SimpleNamespace(
        title="Software Engineering Intern", company="Example", area="Software",
        description="C++ Python software", requirements="C++", preferred_qualifications="Python",
        resume_target="software_engineering", application_type="STANDARD_JOB", analysis=None,
    )
    monkeypatch.setattr(
        "app.services.kospie.rank_kospie_projects",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("KOSPIE scorer leaked")),
    )
    assert generate_local_content(software, profile).classification == "Software Engineering"


def test_kospie_api_creates_immutable_versions(monkeypatch):
    monkeypatch.setattr(
        "app.services.resume_generation._compile_latex_artifact",
        lambda source: (b"%PDF-1.4", 1, 80.0),
    )
    with TestClient(app, headers=security_headers()) as client:
        first = client.post("/api/kospie/resumes")
        assert first.status_code == 200, first.text
        first_payload = deepcopy(first.json()["tailored_content_json"])
        saved = client.put("/api/kospie/profile", json={
            "selected_universities_json": ["TU Munich", "RWTH Aachen", "TU Dresden"],
            "primary_interests_json": ["Embedded Systems", "Digital Systems"],
        })
        assert saved.status_code == 200, saved.text
        second = client.post("/api/kospie/resumes")
        assert second.status_code == 200, second.text
        history = client.get("/api/kospie/resumes").json()
        assert history[0]["version"] == history[1]["version"] + 1
        assert history[1]["tailored_content_json"] == first_payload
