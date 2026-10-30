from copy import deepcopy
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.main import app
from conftest import security_headers
from app.models import GeneratedResume, Job, ResumeProfile, UserProfile
from app.schemas.api import ResumeCertificationItem
from app.services.research_opportunities import analyze_research_opportunity
from app.services.resume_generation import (
    ARTIFICIAL_PHRASES,
    CANONICAL_DEGREE,
    CANONICAL_EMAIL,
    CANONICAL_GITHUB,
    CANONICAL_GRADUATION,
    CANONICAL_GPA,
    CANONICAL_INSTITUTION,
    CANONICAL_LINKEDIN,
    CANONICAL_LINKEDIN_LABEL,
    CANONICAL_LOCATION,
    CANONICAL_NAME,
    CANONICAL_PHONE,
    CANONICAL_STUDENT_TITLE,
    _select_courses,
    fit_resume_to_one_page,
    _validate_pdf_text,
    classify_job,
    generate_local_content,
    latex_escape,
    render_latex,
    resume_filename,
    sanitize_resume_text,
    score_project_for_job,
    validate_generated_resume,
    validate_master_profile,
)


def research_job(description: str = "robotics controls embedded sensing computer vision") -> SimpleNamespace:
    opportunity = job("Visiting Research Intern", description, "Robotics")
    opportunity.resume_target = "robotics_research"
    opportunity.lab = "Robotics Lab"
    opportunity.supervisor = "Professor"
    opportunity.research_areas = ["robotics", "controls"]
    opportunity.opportunity_type = "research"
    return opportunity


def test_robotics_research_ranks_physical_projects_above_generic_web():
    content = generate_local_content(research_job(), profile())
    names = [item.name for item in content.projects]
    assert "MATT Web-Controlled Writing Robot" in names[:3]
    assert "FreeRTOS Event-Driven System" in names[:3]
    assert "Internship Radar - AI Resume Tailoring Platform" not in names[:3]
    assert content.section_order[0] == "education"


def test_software_engineering_ranking_is_unchanged_by_research_target():
    content = generate_local_content(software_job(), profile())
    assert content.classification == "Software Engineering"
    assert content.projects[0].name == "Internship Radar - AI Resume Tailoring Platform"


def test_research_opportunity_cannot_create_unverified_ros_skill():
    candidate = profile()
    candidate.skills_json = [skill for skill in candidate.skills_json if skill != "ROS"]
    opportunity = research_job("ROS SLAM CUDA Gazebo robotics research")
    content = generate_local_content(opportunity, candidate)
    assert "ROS" not in content.selected_skills
    assert "ROS" not in render_latex(content, candidate)


def test_robotics_research_filename_is_sanitized_and_compact():
    filename = resume_filename("Alex Rivera", "University of Washington", "robotics_research", variant="MACS")
    assert filename == "Alex_Rivera_UW_MACS_Research_CV.pdf"
    assert len(filename) <= 124


def test_professor_focus_changes_project_ranking():
    candidate = profile()
    candidate.projects_json.append(project(
        "Python Camera Perception System",
        ["Python", "Computer Vision", "OpenCV"],
        f"{CANONICAL_GITHUB}/camera-perception",
        "camera perception",
    ))
    manipulation = research_job("robotic manipulation tactile sensing motor controls")
    vision = research_job("robot learning perception computer vision image processing")
    manipulation_names = [item.name for item in generate_local_content(manipulation, candidate).projects]
    vision_names = [item.name for item in generate_local_content(vision, candidate).projects]
    assert manipulation_names != vision_names
    assert vision_names.index("Python Camera Perception System") < manipulation_names.index("Python Camera Perception System")


def test_base_research_analysis_works_without_professor_or_lab():
    opportunity = research_job("")
    opportunity.supervisor = ""
    opportunity.lab = ""
    result = analyze_research_opportunity(profile(), opportunity)
    assert result["recommended_projects"]
    assert result["verified_matches"]
    assert result["confidence"] > 0


def test_similarity_analysis_does_not_mutate_previous_resume():
    opportunity = research_job("robotics embedded controls")
    content = generate_local_content(opportunity, profile())
    snapshot = deepcopy(content.model_dump())
    previous = SimpleNamespace(id=77, tailored_content_json=deepcopy(snapshot))
    result = analyze_research_opportunity(profile(), opportunity, [previous])
    assert result["similarity"] >= 85
    assert result["similar_resume_id"] == 77
    assert previous.tailored_content_json == snapshot
from app.services.resume_skills import (
    build_verified_skill_registry,
    canonicalize_skill,
)
from app.services.seed import seed_profile_and_sources


SKILLS = [
    "C", "C++", "Python", "JavaScript", "FreeRTOS", "Tasks", "Queues",
    "Mutexes", "Semaphores", "Interrupts", "ISRs", "UART", "SPI", "I2C",
    "GPIO", "PWM", "ADC", "Timers", "Linux", "Git", "GitHub", "VS Code",
    "MCUXpresso", "PlatformIO", "Oscilloscope", "Logic Analyzer", "Testing",
    "Debugging", "FPGA", "Verilog", "SystemVerilog", "Digital Design",
    "Robotics", "Controls", "ROS", "Computer Vision", "OpenCV", "MySQL",
    "Flask", "File I/O", "Object-Oriented Programming", "Data Structures",
    "Algorithms", "Graph Algorithms", "Path Validation", "REST APIs", "API Development",
    "Next.js", "TypeScript", "FastAPI", "PostgreSQL", "SQLAlchemy", "Pydantic",
    "OpenAI API", "Jinja2", "LaTeX", "Tectonic", "Auth.js", "Docker",
    "Embedded Systems", "Microcontrollers", "FRDM-KL25Z", "ESP32", "Raspberry Pi",
    "Concurrent Programming", "Multithreaded Programming",
    "Hardware/Software Integration", "Hardware Debugging", "Software Debugging",
    "Software Validation", "SQL", "Backend Development", "Full-Stack Development",
    "Intel MAX 10", "Digital Logic", "FPGA Design",
]


def project(name: str, technologies: list[str], url: str, marker: str) -> dict:
    return {
        "name": name,
        "technologies": technologies,
        "github_url": url,
        "bullets": [
            f"Developed modular {marker} components to implement control, data handling, communication, and testing across the academic engineering system.",
            f"Tested {marker} interfaces to isolate implementation faults and validate consistent behavior across the project's principal technical workflows.",
        ],
    }


def test_google_solutions_resume_uses_verified_software_evidence():
    from app.services.resume_generation import classify_job, generate_local_content, score_project_for_job
    from app.services.scoring import _skill_matches

    candidate = profile()
    candidate.skills_json = [skill for skill in candidate.skills_json if skill != "Java"]
    job = SimpleNamespace(
        title="Customer and Partner Solutions Engineering Intern, BS/MS, Summer 2027",
        company="Google", area="Solutions Engineering", description=(
            "Build technical integrations and automation, troubleshoot partner issues, "
            "scope reusable solutions and support developers using RESTful APIs, Python, "
            "data pipelines and dashboards."
        ),
        requirements="", preferred_qualifications="Python, C, C++, Java, JSON, SDKs and Webhooks",
        resume_target="recommended", application_type="STANDARD_JOB",
    )
    assert classify_job(job) == "Solutions / API Integration"
    matched, _, missing, _ = _skill_matches(job, candidate)
    assert "java" not in matched
    assert "java" in missing
    assert "python" in matched and "c++" in matched
    content = generate_local_content(job, candidate)
    names = [item.name for item in content.projects]
    assert names[0] == "Internship Radar - AI Resume Tailoring Platform"
    assert "SkiliAir Air Quality Monitoring System" in names[:3]
    assert "Java" not in content.selected_skills
    assert "SDKs" not in content.selected_skills
    assert "Webhooks" not in content.selected_skills
    assert "Web & APIs" in [group.name for group in content.skill_categories]
    assert "software services" in content.summary
    scores = {item["name"]: item["score"] for item in content.tailoring_trace["project_ranking"]}
    assert scores["SkiliAir Air Quality Monitoring System"] > scores["Intel MAX 10 Robotic Arm Controller"]


def test_google_ranking_with_seeded_project_facts():
    from app.services.seed import INTERNSHIP_RADAR_PROJECT, VERIFIED_RESUME_PROJECTS
    candidate = profile()
    candidate.projects_json = deepcopy(VERIFIED_RESUME_PROJECTS) + [deepcopy(INTERNSHIP_RADAR_PROJECT)]
    candidate.skills_json = sorted({tech for item in candidate.projects_json for tech in item["technologies"]})
    opportunity = SimpleNamespace(
        title="Customer and Partner Solutions Engineering Intern, BS/MS, Summer 2027",
        company="Google", area="Solutions Engineering", resume_target="recommended",
        application_type="STANDARD_JOB", requirements="", preferred_qualifications="Python C C++ Java JSON SDKs Webhooks",
        description="Build technical integrations, automation, REST APIs, data pipelines and dashboards; troubleshoot partner issues.",
    )
    content = generate_local_content(opportunity, candidate)
    assert [item["name"] for item in content.tailoring_trace["project_ranking"][:5]] == [
        "Internship Radar - AI Resume Tailoring Platform",
        "SkiliAir Air Quality Monitoring System",
        "DC Motor Position Control System with WebXR Interface",
        "MATT Web-Controlled Writing Robot",
        "FreeRTOS Event-Driven System",
    ]
    assert "Java" not in content.selected_skills


def test_embedded_job_keeps_firmware_projects_ahead_of_web():
    from app.services.resume_generation import _select_projects
    job = SimpleNamespace(title="Embedded Firmware Intern", description="C FreeRTOS microcontrollers UART interrupts embedded firmware", requirements="", preferred_qualifications="", resume_target="recommended")
    names = [item["name"] for item in _select_projects(job, profile(), "Embedded / Firmware", 7)]
    assert names.index("FreeRTOS Event-Driven System") < names.index("Internship Radar - AI Resume Tailoring Platform")
    assert names.index("MATT Web-Controlled Writing Robot") < names.index("Internship Radar - AI Resume Tailoring Platform")
    content = generate_local_content(job, profile())
    assert {"RTOS", "Protocols", "Embedded Systems"} <= {group.name for group in content.skill_categories}
    assert "firmware" in content.summary


def test_new_santiago_projects_are_available_to_role_specific_resume_selection():
    from app.services.resume_generation import _select_projects
    from app.services.seed import INTERNSHIP_RADAR_PROJECT, VERIFIED_RESUME_PROJECTS

    candidate = profile()
    candidate.projects_json = deepcopy(VERIFIED_RESUME_PROJECTS) + [deepcopy(INTERNSHIP_RADAR_PROJECT)]
    candidate.skills_json = sorted({
        technology
        for project_item in candidate.projects_json
        for technology in project_item.get("technologies", [])
    })

    software_job = SimpleNamespace(
        title="Software Engineering Intern",
        description="Build a browser-based coding platform using TypeScript and offline tools.",
        requirements="Programming tools, local execution, and persistent learning progress.",
        preferred_qualifications="",
        resume_target="recommended",
    )
    software_names = [
        item["name"]
        for item in _select_projects(software_job, candidate, "Software Engineering", 4)
    ]
    assert "Forge the Code" in software_names

    embedded_job = SimpleNamespace(
        title="Embedded Bluetooth Firmware Intern",
        description="ESP32, C++, BLE, HID peripherals, and device integration.",
        requirements="",
        preferred_qualifications="",
        resume_target="recommended",
    )
    embedded_names = [
        item["name"]
        for item in _select_projects(embedded_job, candidate, "Embedded / Firmware", 4)
    ]
    assert "BLE Virtual Mouse" in embedded_names

    vision_job = SimpleNamespace(
        title="Computer Vision Intern",
        description="Python, OpenCV, image processing, and visual classification.",
        requirements="",
        preferred_qualifications="",
        resume_target="recommended",
    )
    vision_names = [
        item["name"]
        for item in _select_projects(vision_job, candidate, "Computer Vision", 4)
    ]
    assert vision_names[0] == "Fruit Freshness Detector"

    all_projects = [
        item["name"]
        for item in _select_projects(software_job, candidate, "Software Engineering", 20)
    ]
    assert "C.U.T.Y Desktop Companion Robot" in all_projects
    assert "Fruit Freshness Detector" in all_projects
    assert "ESP32 Discrete PID Controller with Analog Reference" in all_projects
    assert "DC Motor Position Control System with WebXR Interface" in all_projects

    from app.services.resume_generation import score_project_for_job
    from app.services.seed import VERIFIED_RESUME_PROJECTS
    control_projects = {
        item["name"]: item
        for item in VERIFIED_RESUME_PROJECTS
        if item["name"] in {
            "ESP32 Discrete PID Controller with Analog Reference",
            "DC Motor Position Control System with WebXR Interface",
        }
    }
    discrete_pid_job = "ESP32 discrete PID control using analog reference ADC, DAC, integral and derivative terms"
    motor_position_job = "ESP32 DC motor position control using encoder feedback, BTS7960, PWM, MQTT and WebXR"
    assert score_project_for_job(
        control_projects["ESP32 Discrete PID Controller with Analog Reference"],
        "Embedded / Firmware",
        discrete_pid_job,
    ) > score_project_for_job(
        control_projects["DC Motor Position Control System with WebXR Interface"],
        "Embedded / Firmware",
        discrete_pid_job,
    )
    assert score_project_for_job(
        control_projects["DC Motor Position Control System with WebXR Interface"],
        "Embedded / Firmware",
        motor_position_job,
    ) > score_project_for_job(
        control_projects["ESP32 Discrete PID Controller with Analog Reference"],
        "Embedded / Firmware",
        motor_position_job,
    )


def test_seeded_verified_registry_excludes_legacy_java_claim():
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        current = db.query(ResumeProfile).first()
        assert current is not None
        assert "Java" not in build_verified_skill_registry(current)


def test_graduation_mm_yy_only_when_posting_requests_it():
    from app.services.resume_generation import _job_education
    ordinary = SimpleNamespace(description="Software engineering internship", requirements="", preferred_qualifications="")
    formatted = SimpleNamespace(description="List your expected graduation date in MM/YY format", requirements="", preferred_qualifications="")
    assert _job_education(profile(), ordinary)["graduation"] == CANONICAL_GRADUATION
    assert _job_education(profile(), formatted)["graduation"] == "Expected Graduation: 06/28"


def profile() -> SimpleNamespace:
    return SimpleNamespace(
        full_name=CANONICAL_NAME,
        email=CANONICAL_EMAIL,
        phone=CANONICAL_PHONE,
        location=CANONICAL_LOCATION,
        linkedin_url=CANONICAL_LINKEDIN,
        github_url=CANONICAL_GITHUB,
        headline=CANONICAL_STUDENT_TITLE,
        summary="Canonical engineering profile.",
        education_json=[{
            "institution": CANONICAL_INSTITUTION,
            "degree": CANONICAL_DEGREE,
            "location": CANONICAL_LOCATION,
            "graduation": CANONICAL_GRADUATION,
            "gpa": CANONICAL_GPA,
            "coursework": [],
        }],
        skills_json=SKILLS,
        experience_json=[],
        projects_json=[
            {
                "name": "Internship Radar - AI Resume Tailoring Platform",
                "status": "In progress / near completion",
                "technologies": [
                    "Next.js", "TypeScript", "FastAPI", "Python", "PostgreSQL",
                    "SQLAlchemy", "Pydantic", "OpenAI API", "Jinja2", "LaTeX",
                    "Tectonic", "Auth.js", "Git", "Docker",
                ],
                "repository_url": "https://github.com/example-candidate/Intership_radar",
                "live_url": "",
                "is_public": True,
                "is_resume_eligible": True,
                "bullets": [
                    "Built a full-stack platform that tracks internship opportunities and generates tailored, ATS-compatible resumes from verified user profile data.",
                    "Implemented structured AI generation, validation rules, dynamic Jinja2 and LaTeX templates, and automated PDF compilation for consistent one-page resumes.",
                    "Developed authenticated job tracking, resume versioning, PDF preview and download, LaTeX source viewing, and job-specific project selection.",
                ],
            },
            project("MATT Web-Controlled Writing Robot", ["C", "C++", "UART", "PWM"], CANONICAL_GITHUB, "robotic"),
            project("FreeRTOS Event-Driven System", ["C", "FreeRTOS", "Tasks", "Queues"], CANONICAL_GITHUB, "real-time"),
            project("SkiliAir Air Quality Monitoring System", ["Python", "Flask", "REST APIs", "MySQL"], f"{CANONICAL_GITHUB}/raspberrypi-air-quality-monitor", "monitoring"),
            project("Stock Exchange Matching Engine", ["C++", "Data Structures", "Algorithms", "File I/O"], f"{CANONICAL_GITHUB}/trading-simulator-v", "matching"),
            {
                "name": "Königsberg Graph Game",
                "technologies": [
                    "C++", "Object-Oriented Programming", "Graph Algorithms",
                    "Algorithms", "Path Validation", "Data Structures", "Testing",
                ],
                "github_url": f"{CANONICAL_GITHUB}/Konigsberg-game",
                "bullets": [
                    "Developed a modular C++ graph application modeling locations, bridges, vertices, edges, and valid movement paths using object-oriented components.",
                    "Implemented graph traversal and path-validation algorithms to evaluate available routes and maintain consistent application state.",
                    "Tested valid and invalid movement sequences to verify graph constraints, path updates, and behavior across multiple configurations.",
                ],
            },
            project("Intel MAX 10 Robotic Arm Controller", ["FPGA", "Verilog", "SystemVerilog", "PWM"], f"{CANONICAL_GITHUB}/Verilog", "digital"),
        ],
        coursework_json=[
            {
                "name": "Python Data Structures",
                "institution": "University of Michigan",
                "issued": "September 2024",
                "areas": ["Python", "Data Structures", "Software Engineering"],
                "priority": "normal",
            },
            {
                "name": "Using Python to Access Web Data",
                "institution": "University of Michigan",
                "issued": "November 2024",
                "areas": ["Python", "Web Data", "APIs", "Backend"],
                "priority": "normal",
            },
            {
                "name": "Programming for Everybody (Getting Started with Python)",
                "institution": "University of Michigan",
                "issued": "September 2024",
                "areas": ["Python Fundamentals"],
                "priority": "low",
            },
        ],
        certifications_json=[],
        languages_json=[
            "Spanish — Native",
            "English — Fluent",
            "French — Basic",
            "German — Basic",
        ],
        forbidden_claims_json=["C#", ".NET", "MCP", "AWS certification"],
    )


def job(title: str, description: str, area: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        company="Test Company",
        area=area,
        description=description,
        requirements="",
        preferred_qualifications="",
        analysis=None,
    )


def embedded_job() -> SimpleNamespace:
    return job(
        "Embedded Software Engineer Intern",
        "Develop C and C++ firmware with FreeRTOS, UART, SPI, GPIO, PWM, interrupts, and microcontrollers.",
        "Embedded",
    )


def software_job() -> SimpleNamespace:
    return job(
        "Software Engineering Intern",
        "Build C++ and Python software using object-oriented programming, data structures, algorithms, Linux, Git, REST APIs, and testing.",
        "Software",
    )


def maps_job(description: str | None = None) -> SimpleNamespace:
    return job(
        "Maps Intern",
        description or (
            "Build path planning services that generate routes from graph nodes and edges. "
            "Improve routing algorithms, spatial data transformation, APIs, validation, "
            "automated testing, and tools for autonomous vehicles."
        ),
        "Maps",
    )


def backend_job() -> SimpleNamespace:
    return job(
        "Backend Engineering Intern",
        "Build Python FastAPI services, REST APIs, PostgreSQL models, SQLAlchemy persistence, and authenticated backend workflows.",
        "Backend",
    )


def ai_api_job() -> SimpleNamespace:
    return job(
        "AI API Software Engineering Intern",
        "Integrate the OpenAI API using Python, structured outputs, Pydantic validation, APIs, and automated testing.",
        "AI",
    )


def full_stack_job() -> SimpleNamespace:
    return job(
        "Full-Stack Engineering Intern",
        "Build a Next.js and TypeScript web platform with FastAPI, PostgreSQL, authenticated routes, APIs, and testing.",
        "Web",
    )


def test_latex_special_characters_are_escaped():
    escaped = latex_escape(r"C&C_100% #1 $x {ok} ~ ^ \\")
    for token in (r"\&", r"\_", r"\%", r"\#", r"\$", r"\{", r"\}", r"\textasciitilde", r"\textasciicircum"):
        assert token in escaped


def test_canonical_degree_is_always_used():
    content = generate_local_content(embedded_job(), profile())
    assert content.education.degree == CANONICAL_DEGREE
    assert CANONICAL_STUDENT_TITLE in content.headline
    assert "Robotics and Digital Systems Engineering student" in content.summary


def test_core_languages_are_always_included_and_basic_languages_are_contextual():
    standard = generate_local_content(software_job(), profile())
    assert standard.languages == ["Spanish - Native", "English - Fluent"]

    french_role = job(
        "Software Engineering Intern",
        "Build Python services with a team in France; French language is helpful.",
    )
    tailored = generate_local_content(french_role, profile())
    assert tailored.languages == [
        "Spanish - Native",
        "English - Fluent",
        "French - Basic",
    ]
    assert "German - Basic" not in tailored.languages


def test_languages_render_as_a_real_resume_section():
    latex = render_latex(generate_local_content(software_job(), profile()), profile())
    assert r"\sectionheading{Languages}" in latex
    assert "Spanish" in latex
    assert "English" in latex


def test_every_resume_target_uses_projects_as_the_section_heading():
    base_content = generate_local_content(software_job(), profile())
    for application_type, classification in (
        ("STANDARD_JOB", "Software Engineering"),
        ("TALENT_COMMUNITY", "Talent Community"),
        ("KOSPIE_PROGRAM", "KOSPIE / Germany Engineering"),
        ("STANDARD_JOB", "Robotics Research"),
    ):
        content = base_content.model_copy(deep=True)
        content.application_type = application_type
        content.classification = classification
        latex = render_latex(content, profile())
        assert r"\sectionheading{Projects}" in latex
        assert r"\sectionheading{Project Experience}" not in latex
        assert r"\sectionheading{Engineering Projects}" not in latex
        assert r"\sectionheading{Robotics and Embedded Projects}" not in latex


def test_santiago_linkedin_is_canonicalized_in_visible_and_hidden_latex():
    candidate = profile()
    candidate.linkedin_url = (
        "https://www.linkedin.com/in/example-candidate/"
    )
    latex = render_latex(generate_local_content(software_job(), candidate), candidate)

    assert (
        rf"\href{{{CANONICAL_LINKEDIN}}}{{{CANONICAL_LINKEDIN_LABEL}}}"
        in latex
    )
    assert "example-legacy-candidate" not in latex


def test_inconsistent_degree_name_is_rejected():
    content = generate_local_content(software_job(), profile())
    content.education.degree = "Robotics and Intelligent Systems Engineering"
    with pytest.raises(ValueError, match="degree"):
        validate_generated_resume(content, profile(), software_job())


def test_noncanonical_email_is_rejected():
    bad_profile = profile()
    bad_profile.email = "wrong@example.com"
    with pytest.raises(ValueError, match="email"):
        validate_master_profile(bad_profile)


def test_seed_repairs_legacy_resume_identity():
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        stored = db.query(ResumeProfile).first()
        assert stored is not None
        stored.email = settings.resume_email
        stored.phone = ""
        stored.location = "Mexico"
        stored.linkedin_url = ""
        stored.github_url = ""
        stored.headline = CANONICAL_DEGREE
        stored.education_json = [{
            "institution": CANONICAL_INSTITUTION,
            "degree": CANONICAL_DEGREE,
            "location": "Mexico",
            "graduation": "2028",
            "gpa": "93.05/100.0",
            "coursework": [],
        }]
        db.commit()

        seed_profile_and_sources(db)
        db.refresh(stored)

        validate_master_profile(stored)
        assert stored.user_id == settings.primary_user_id
        assert stored.email == CANONICAL_EMAIL
        assert stored.email == "candidate@example.com"
        assert stored.linkedin_url == CANONICAL_LINKEDIN
        assert stored.github_url == CANONICAL_GITHUB
        notification_profile = db.query(UserProfile).first()
        assert notification_profile is not None
        assert notification_profile.notification_email == settings.email_recipient
        eligible_projects = [
            item for item in stored.projects_json
            if item.get("is_resume_eligible", True)
        ]
        assert len(eligible_projects) >= 7
        assert all(len(item.get("bullets") or []) >= 2 for item in eligible_projects)
        generated = generate_local_content(software_job(), stored)
        validate_generated_resume(generated, stored, software_job())
        rendered = render_latex(generated, stored)
        assert CANONICAL_EMAIL in rendered
        assert settings.notification_email not in rendered


def test_linkedin_migration_updates_only_santiago_candidate_profiles():
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260914_25_santiago_linkedin.py"
    )
    spec = importlib.util.spec_from_file_location("linkedin_migration", path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        for table_name, owner_column in (
            ("user_profiles", "owner_user_id"),
            ("resume_profiles", "user_id"),
            ("application_profiles", "owner_user_id"),
        ):
            connection.exec_driver_sql(
                f"CREATE TABLE {table_name} ("
                f"{owner_column} VARCHAR(320) PRIMARY KEY, "
                "full_name VARCHAR(160), linkedin_url TEXT)"
            )
            connection.exec_driver_sql(
                f"INSERT INTO {table_name} VALUES "
                "('santiago', 'Alex Rivera', 'https://old.example/santiago'), "
                "('joshua', 'Taylor Morgan', 'https://www.linkedin.com/in/example-candidate/')"
            )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        for table_name in (
            "user_profiles", "resume_profiles", "application_profiles",
        ):
            rows = connection.exec_driver_sql(
                f"SELECT full_name, linkedin_url FROM {table_name} ORDER BY full_name"
            ).all()
            assert rows == [
                ("Taylor Morgan", "https://www.linkedin.com/in/example-candidate/"),
                ("Alex Rivera", CANONICAL_LINKEDIN),
            ]


def test_artificial_phrases_are_rejected():
    content = generate_local_content(embedded_job(), profile())
    content.summary = (
        "Robotics and Digital Systems Engineering student with documented application behavior "
        "across embedded systems, firmware, interfaces, and robotic projects. Developed C/C++ "
        "software using FreeRTOS, UART, SPI, Linux, and testing for multidisciplinary academic "
        "hardware platforms and integrated control applications."
    )
    with pytest.raises(ValueError, match="artificial"):
        validate_generated_resume(content, profile(), embedded_job())
    assert "documented application behavior" in ARTIFICIAL_PHRASES


def test_skill_categories_never_have_one_item():
    for current_job in (embedded_job(), software_job()):
        content = generate_local_content(current_job, profile())
        assert all(2 <= len(group.items) <= 8 for group in content.skill_categories)
        assert len(content.skill_categories) <= 4


def test_embedded_project_priority():
    content = generate_local_content(embedded_job(), profile())
    assert [item.name for item in content.projects[:3]] == [
        "FreeRTOS Event-Driven System",
        "MATT Web-Controlled Writing Robot",
        "Intel MAX 10 Robotic Arm Controller",
    ]


def test_software_project_priority():
    content = generate_local_content(software_job(), profile())
    assert [item.name for item in content.projects[:3]] == [
        "Internship Radar - AI Resume Tailoring Platform",
        "Stock Exchange Matching Engine",
        "Königsberg Graph Game",
    ]


@pytest.mark.parametrize("term", ["maps", "routing", "navigation"])
def test_maps_terms_use_maps_classification(term):
    assert classify_job(job(f"{term.title()} Intern", f"Build {term} services")) == (
        "Maps / Routing / Geospatial"
    )


def test_data_alone_does_not_trigger_maps_classification():
    assert classify_job(job("Data Engineering Intern", "Build SQL data pipelines")) == "Backend / Data"


def test_maps_project_order_prioritizes_graph_relevance():
    content = generate_local_content(maps_job(), profile())
    assert [item.name for item in content.projects[:3]] == [
        "Königsberg Graph Game",
        "SkiliAir Air Quality Monitoring System",
        "Internship Radar - AI Resume Tailoring Platform",
    ]


def test_stock_project_cannot_win_from_technology_count_alone():
    current_profile = profile()
    graph = next(item for item in current_profile.projects_json if "Graph Game" in item["name"])
    stock = next(item for item in current_profile.projects_json if item["name"].startswith("Stock"))
    requirements = maps_job().description
    assert score_project_for_job(
        graph, "Maps / Routing / Geospatial", requirements
    ) > score_project_for_job(stock, "Maps / Routing / Geospatial", requirements)


def test_maps_content_does_not_invent_gis_experience():
    content = generate_local_content(maps_job(), profile())
    rendered = " ".join([
        content.headline,
        content.summary,
        *[item for group in content.skill_categories for item in group.items],
    ]).lower()
    for unsupported in ("gis", "gps", "slam", "mapbox", "openstreetmap", "geospatial database"):
        assert unsupported not in rendered
    assert "geospatial engineer" not in content.headline.lower()
    assert "professional" not in content.summary.lower()


def test_maps_headline_and_skill_groups_are_bounded():
    content = generate_local_content(maps_job(), profile())
    assert content.headline == (
        "Robotics and Digital Systems Engineering Student | C++ | Python | Algorithms"
    )
    assert content.headline.count("|") == 3
    assert len(content.skill_categories) <= 4
    assert all(len(group.items) >= 2 for group in content.skill_categories)


def test_maps_projects_show_at_most_five_verified_technologies():
    content = generate_local_content(maps_job(), profile())
    assert 3 <= len(content.projects) <= 4
    assert all(len(item.technologies) <= 5 for item in content.projects)
    validate_generated_resume(content, profile(), maps_job())


def test_maps_github_links_are_verified_https_links():
    content = generate_local_content(maps_job(), profile())
    assert all(
        item.github_url.startswith("https://github.com/example-candidate")
        for item in content.projects if item.github_url is not None
    )


def test_internship_radar_is_verified_and_resume_eligible():
    radar = next(
        item for item in profile().projects_json
        if item["name"] == "Internship Radar - AI Resume Tailoring Platform"
    )
    assert radar["is_resume_eligible"] is True
    assert radar["status"] == "In progress / near completion"
    assert radar["is_public"] is True


def test_internship_radar_leads_full_stack_and_software():
    assert generate_local_content(full_stack_job(), profile()).projects[0].name.startswith(
        "Internship Radar"
    )
    assert generate_local_content(software_job(), profile()).projects[0].name.startswith(
        "Internship Radar"
    )


def test_internship_radar_leads_backend_and_ai_api():
    assert generate_local_content(backend_job(), profile()).projects[0].name.startswith(
        "Internship Radar"
    )
    assert generate_local_content(ai_api_job(), profile()).projects[0].name.startswith(
        "Internship Radar"
    )


def test_internship_radar_does_not_displace_pure_embedded_projects():
    names = [
        item.name for item in generate_local_content(embedded_job(), profile()).projects
    ]
    assert names[:3] == [
        "FreeRTOS Event-Driven System",
        "MATT Web-Controlled Writing Robot",
        "Intel MAX 10 Robotic Arm Controller",
    ]


def test_private_internship_radar_has_no_github_or_live_link():
    current_profile = profile()
    radar_source = next(
        item for item in current_profile.projects_json
        if item["name"].startswith("Internship Radar")
    )
    radar_source["is_public"] = False
    content = generate_local_content(full_stack_job(), current_profile)
    radar = content.projects[0]
    assert radar.github_url is None
    assert radar.live_url is None
    latex = render_latex(content, current_profile)
    radar_heading = latex.split("Internship Radar", 1)[1].split("\\begin{itemize}", 1)[0]
    assert "[GitHub]" not in radar_heading
    assert "[Live]" not in radar_heading


def test_public_internship_radar_uses_verified_github_link():
    content = generate_local_content(full_stack_job(), profile())
    radar = content.projects[0]
    assert radar.github_url == "https://github.com/example-candidate/Intership_radar"


def test_internship_radar_bullets_do_not_invent_metrics_or_deployment():
    for current_job in (software_job(), backend_job(), ai_api_job(), full_stack_job()):
        content = generate_local_content(current_job, profile())
        radar = next(item for item in content.projects if item.name.startswith("Internship Radar"))
        text = " ".join(radar.bullets).lower()
        for unsupported in (
            "thousands of users", "revenue", "used by companies", "deployed",
            "kubernetes", "aws", "ci/cd",
        ):
            assert unsupported not in text


def test_course_selection_is_relevant_bounded_and_low_priority_filtered():
    software_courses = _select_courses(software_job(), profile(), "Software Engineering")
    assert len(software_courses) <= 2
    assert software_courses[0]["name"] == "Python Data Structures"
    assert all(
        item["name"] != "Programming for Everybody (Getting Started with Python)"
        for item in software_courses
    )
    backend_courses = _select_courses(backend_job(), profile(), "Backend / Data")
    assert [item["name"] for item in backend_courses] == [
        "Using Python to Access Web Data",
        "Python Data Structures",
    ]


def test_embedded_and_fpga_omit_python_courses():
    assert _select_courses(embedded_job(), profile(), "Embedded / Firmware") == []
    assert _select_courses(
        job("FPGA Intern", "Verilog RTL FPGA digital design"),
        profile(),
        "FPGA / Digital Design",
    ) == []


def test_generated_content_limits_projects_and_courses():
    for current_job in (
        embedded_job(), software_job(), backend_job(), ai_api_job(),
        maps_job(), full_stack_job(),
    ):
        content = generate_local_content(current_job, profile(), project_limit=4)
        assert len(content.projects) <= 4
        assert len(content.coursework) <= 2


def test_unverified_certification_is_rejected():
    content = generate_local_content(software_job(), profile())
    content.certifications = [ResumeCertificationItem(name="AWS certification")]
    with pytest.raises(ValueError, match="certification|forbidden"):
        validate_generated_resume(content, profile(), software_job())


def test_soft_hyphen_and_control_characters_are_removed():
    assert sanitize_resume_text("cross\u00adplatform\x00 software") == "crossplatform software"


def test_pdf_text_validator_rejects_corrupt_characters():
    class Page:
        def extract_text(self):
            return f"{CANONICAL_DEGREE} bad\ufffdtext"

    with pytest.raises(RuntimeError, match="corrupt"):
        _validate_pdf_text(SimpleNamespace(pages=[Page()]))


def test_project_links_must_be_verified_https_urls():
    content = generate_local_content(software_job(), profile())
    content.projects[0].github_url = "http://example.com/not-verified"
    with pytest.raises(ValueError, match="URL"):
        validate_generated_resume(content, profile(), software_job())


def test_classification_supports_embedded_software_and_robotics():
    assert classify_job(embedded_job()) == "Embedded / Firmware"
    assert classify_job(job(
        "Backend Software Engineering Intern",
        "Build Python REST APIs with FastAPI, PostgreSQL, and SQL.",
    )) == "Backend / Data"
    assert classify_job(job("Controls Engineer Intern", "robot motion control and autonomous systems")) == "Robotics / Controls"


def test_google_hardware_recommended_focus_is_not_outvoted_by_software_keywords():
    opportunity = job(
        "Hardware Engineering Intern, BS/MS, Summer 2027",
        "Hardware system integration, system validation, computer architecture, FPGAs, "
        "embedded systems, prototyping, testing and debugging. " + "software Python algorithms " * 30,
    )
    opportunity.preferred_qualifications = (
        "Board design, board bring-up, signal and power integrity, PCB layout, CAD, "
        "mechanical/thermal design, electromechanical assemblies, RF and manufacturing."
    )
    content = generate_local_content(opportunity, profile())
    assert content.classification == "Hardware / Systems Integration"
    assert "Hardware/Software Integration" in content.headline
    assert {project.name for project in content.projects[:3]} == {
        "Intel MAX 10 Robotic Arm Controller",
        "MATT Web-Controlled Writing Robot",
        "FreeRTOS Event-Driven System",
    }
    assert "FPGA" in content.selected_skills
    assert not {"PCB", "CAD", "RF", "Thermal Analysis", "Board Bring-Up"} & set(content.selected_skills)
    assert not any(term in content.summary.lower() for term in ("pcb", "cad", "thermal", "manufacturing"))


def test_explicit_resume_target_remains_a_candidate_choice():
    opportunity = job("Hardware Engineering Intern", "FPGA and embedded systems")
    opportunity.resume_target = "software_engineering"
    assert classify_job(opportunity) == "Software Engineering"
    opportunity.resume_target = "hardware_engineering"
    assert classify_job(opportunity) == "Hardware / Systems Integration"


def test_generated_resume_quality_checks_pass():
    content = generate_local_content(software_job(), profile())
    checks = content.quality_checks
    assert checks.canonical_degree_name
    assert checks.no_unsupported_claims
    assert checks.no_artificial_language
    assert checks.ats_text_clean


def test_project_bullets_meet_word_limits_and_action_verbs():
    content = generate_local_content(embedded_job(), profile())
    for item in content.projects:
        assert 2 <= len(item.bullets) <= 3
        for bullet in item.bullets:
            assert 14 <= len(bullet.split()) <= 28


def test_duplicate_bullets_are_rejected():
    content = generate_local_content(software_job(), profile())
    content.projects[1].bullets[0] = content.projects[0].bullets[0]
    with pytest.raises(ValueError, match="duplicate"):
        validate_generated_resume(content, profile(), software_job())


def test_generate_latest_pdf_and_tex(monkeypatch):
    sample = generate_local_content(software_job(), profile())
    monkeypatch.setattr(
        "app.main.generate_resume",
        lambda current_job, current_profile, generation_id: (
            sample,
            "\\documentclass{article}",
            b"%PDF-1.4",
        ),
    )
    monkeypatch.setattr("app.main.compile_latex", lambda source: b"%PDF-1.4 test")
    with TestClient(app, headers=security_headers()) as client:
        jobs = client.get("/api/jobs", params={"page_size": 1}).json()["items"]
        headers = security_headers()
        response = client.post(f"/api/jobs/{jobs[0]['id']}/resume/generate", headers=headers)
        assert response.status_code == 200, response.text
        resume = response.json()
        assert resume["status"] == "compiled"
        assert resume["selected_skills"] == sample.selected_skills
        assert resume["skill_categories"] == [
            group.model_dump() for group in sample.skill_categories
        ]
        assert resume["job_skill_matches"]
        assert resume["skill_verification"]["registry_size"] > 0
        pdf = client.get(resume["pdf_url"], headers=headers)
        assert pdf.status_code == 200
        tex = client.get(resume["tex_url"], headers=headers)
        assert tex.status_code == 200


def test_manual_research_opportunity_generates_without_job_url(monkeypatch):
    sample = generate_local_content(research_job(), profile())
    monkeypatch.setattr(
        "app.main.generate_resume",
        lambda current_job, current_profile, generation_id: (
            sample, "\\documentclass{article}", b"%PDF-1.4",
        ),
    )
    with TestClient(app, headers=security_headers()) as client:
        created = client.post("/api/research-opportunities", json={
            "organization": "University of Washington",
            "title": "Visiting Research Intern",
            "lab": "MACS Lab",
            "professor": "Xu Chen",
            "research_areas": ["robotics", "controls", "computer vision"],
            "description": "Robotics controls computer vision ROS SLAM CUDA",
        })
        assert created.status_code == 201, created.text
        opportunity = created.json()
        assert opportunity["opportunity_type"] == "research"
        assert opportunity["source_url"] == ""
        analyzed = client.post(f"/api/research-opportunities/{opportunity['id']}/analyze")
        assert analyzed.status_code == 200, analyzed.text
        assert {"SLAM", "CUDA"} <= set(analyzed.json()["unverified_keywords"])
        assert analyzed.json()["recommended_projects"]
        generated = client.post(
            f"/api/jobs/{opportunity['id']}/resume/generate",
            json={"resume_target": "robotics_research"},
        )
        assert generated.status_code == 200, generated.text
        assert generated.json()["resume_target"] == "robotics_research"


def _selected(content) -> list[str]:
    return [item for group in content.skill_categories for item in group.items]


def test_every_resume_has_compact_verified_skills_section():
    registry = build_verified_skill_registry(profile())
    for current_job in (
        software_job(), embedded_job(), backend_job(), full_stack_job(),
        job("FPGA Design Intern", "Design Verilog FPGA RTL and digital logic."),
    ):
        content = generate_local_content(current_job, profile())
        selected = _selected(content)
        assert 8 <= len(selected) <= 16
        assert 2 <= len(content.skill_categories) <= 4
        assert set(selected) <= set(registry)
        assert content.selected_skills == selected


def test_job_keywords_control_skill_priority():
    cpp = generate_local_content(
        job("Software Engineer Intern", "C++ is required. Build C++ software on Linux."),
        profile(),
    )
    python = generate_local_content(
        job("Software Engineer Intern", "Python is required. Build Python services and algorithms."),
        profile(),
    )
    assert cpp.selected_skills.index("C++") < cpp.selected_skills.index("Python")
    assert python.selected_skills.index("Python") < python.selected_skills.index("C++")
    assert cpp.selected_skills != python.selected_skills


def test_role_aware_selection_for_embedded_backend_and_fpga():
    embedded = generate_local_content(embedded_job(), profile()).selected_skills
    backend = generate_local_content(backend_job(), profile()).selected_skills
    fpga = generate_local_content(
        job(
            "FPGA Digital Design Intern",
            "Required Verilog and FPGA design. Develop digital logic with GPIO and PWM.",
        ),
        profile(),
    ).selected_skills
    assert {"FreeRTOS", "Embedded Systems", "C"} <= set(embedded)
    assert {"FastAPI", "PostgreSQL", "Python"} <= set(backend)
    assert {"Verilog", "FPGA"} <= set(fpga)


def test_unverified_job_terms_are_removed_not_invented():
    intel = generate_local_content(
        job(
            "Intel Software Engineer Intern",
            "Required C++, Python, Linux, multithreaded programming, x86 Assembly, "
            "Intel Xeon internals, debugging, and software validation.",
        ),
        profile(),
    )
    assert "C++" in intel.selected_skills
    assert "Multithreaded Programming" in intel.selected_skills
    assert "x86 Assembly" not in intel.selected_skills
    assert "Intel Xeon" not in intel.selected_skills
    assert all("x86" not in skill.lower() for skill in intel.selected_skills)


def test_c_does_not_count_as_an_exact_cplusplus_requirement():
    content = generate_local_content(
        job("Software Engineer Intern", "Required: C++ development on Linux."),
        profile(),
    )
    c_match = next(item for item in content.job_skill_matches if item.skill == "C")
    cpp_match = next(item for item in content.job_skill_matches if item.skill == "C++")
    assert c_match.job_occurrences == 0
    assert cpp_match.match_type == "required"


def test_validation_filters_an_injected_unverified_skill_with_warning():
    current_job = software_job()
    content = generate_local_content(current_job, profile())
    content.skill_categories[0].items.insert(0, "x86 Assembly")
    validate_generated_resume(content, profile(), current_job)
    assert "x86 Assembly" not in content.selected_skills
    assert "x86 Assembly" in content.skill_verification.removed
    assert any("Removed unverified skills" in warning for warning in content.warnings)


def test_aliases_canonicalize_without_duplicates():
    current_profile = profile()
    current_profile.skills_json.extend(["cpp", "C/C++", "C plus plus", "Postgres", "RTOS"])
    registry = build_verified_skill_registry(current_profile)
    assert canonicalize_skill("cpp") == "C++"
    assert canonicalize_skill("C/C++") == "C++"
    assert canonicalize_skill("Postgres") == "PostgreSQL"
    assert list(registry).count("C++") == 1
    selected = generate_local_content(software_job(), current_profile).selected_skills
    assert selected.count("C++") == 1


def test_skill_section_is_plain_ats_readable_latex():
    content = generate_local_content(backend_job(), profile())
    latex = render_latex(content, profile())
    assert r"\sectionheading{Skills}" in latex
    assert r"\skillsrow" in latex
    assert "progressbar" not in latex.lower()
    assert "stars" not in latex.lower()
    for skill in content.selected_skills:
        assert latex_escape(skill) in latex


def test_project_supported_skill_can_appear_without_exact_job_keyword():
    content = generate_local_content(
        job("Embedded Firmware Intern", "Develop reliable firmware for microcontroller products."),
        profile(),
    )
    assert "FreeRTOS" in content.selected_skills
    match = next(item for item in content.job_skill_matches if item.skill == "FreeRTOS")
    assert any(evidence.startswith("Project:") for evidence in match.evidence)


def test_skill_tailoring_does_not_remove_top_projects():
    assert [item.name for item in generate_local_content(embedded_job(), profile()).projects[:3]] == [
        "FreeRTOS Event-Driven System",
        "MATT Web-Controlled Writing Robot",
        "Intel MAX 10 Robotic Arm Controller",
    ]
    assert generate_local_content(backend_job(), profile()).projects[0].name.startswith(
        "Internship Radar"
    )


def test_four_projects_are_preferred_by_default():
    assert len(generate_local_content(software_job(), profile()).projects) == 4
    assert len(generate_local_content(embedded_job(), profile()).projects) == 4


def test_simple_laboratory_practice_is_not_used_as_fourth_project():
    candidate = profile()
    strong_names = {"Internship Radar - AI Resume Tailoring Platform", "Stock Exchange Matching Engine", "Königsberg Graph Game"}
    candidate.projects_json = [item for item in candidate.projects_json if item["name"] in strong_names]
    candidate.projects_json.append({
        "name": "PWM classroom practice", "project_type": "laboratory practice",
        "is_resume_eligible": True, "technologies": ["ESP32", "PWM"],
        "bullets": [
            "Configured a simple PWM output on an ESP32 development board to change the brightness of a single LED.",
            "Tested the classroom example by adjusting duty cycle values and observing the resulting brightness changes on the LED.",
        ],
    })
    content = generate_local_content(software_job(), candidate)
    assert len(content.projects) == 3
    assert "PWM classroom practice" not in {project.name for project in content.projects}


def test_four_projects_fit_by_shortening_bullets_before_removing_project(monkeypatch):
    current_job = software_job()
    content = generate_local_content(current_job, profile())
    original_names = [project.name for project in content.projects]
    monkeypatch.setattr("app.services.resume_generation._trim_lowest_priority_skill", lambda *_: False)
    # Capture the actual fitted content rather than the input copy.
    rendered = []
    def render(fitted, _profile):
        rendered.append(fitted.model_copy(deep=True))
        return "latex"
    monkeypatch.setattr("app.services.resume_generation.render_latex", render)
    monkeypatch.setattr("app.services.resume_generation._compile_latex_artifact",
                        lambda _: (b"overflow", 2, 100) if any(len(p.bullets) > 2 for p in rendered[-1].projects) else (b"fit", 1, 90))
    fitted, _, pdf, _ = fit_resume_to_one_page(content, current_job, profile())
    assert [project.name for project in fitted.projects] == original_names
    assert len(fitted.projects) == 4 and pdf == b"fit"


def test_resume_studio_portfolio_keeps_four_projects_within_two_pages(monkeypatch):
    current_profile = profile()
    current_job = software_job()
    current_job.application_type = "PROFILE_PORTFOLIO"
    content = generate_local_content(current_job, current_profile)
    assert len(content.projects) == 4

    monkeypatch.setattr(
        "app.services.resume_generation.render_latex", lambda *_: "latex"
    )
    monkeypatch.setattr(
        "app.services.resume_generation._compile_latex_artifact",
        lambda _: (b"two-pages", 2, 90),
    )

    fitted, _, pdf, _ = fit_resume_to_one_page(content, current_job, current_profile)

    assert len(fitted.projects) == 4
    assert pdf == b"two-pages"
    assert fitted.quality_checks.one_page is False
    assert fitted.quality_checks.within_two_pages is True


def test_overflowing_fourth_is_not_readded_in_underfilled_page(monkeypatch):
    current_job = software_job()
    content = generate_local_content(current_job, profile())
    for project in content.projects:
        project.bullets = project.bullets[:2]
    monkeypatch.setattr("app.services.resume_generation._trim_lowest_priority_skill", lambda *_: False)
    rendered = []
    def render(fitted, _profile):
        rendered.append(fitted.model_copy(deep=True))
        return "latex"
    monkeypatch.setattr("app.services.resume_generation.render_latex", render)
    monkeypatch.setattr("app.services.resume_generation._compile_latex_artifact",
                        lambda _: (b"overflow", 2, 100) if len(rendered[-1].projects) == 4 else (b"fit", 1, 70))
    fitted, _, pdf, _ = fit_resume_to_one_page(content, current_job, profile())
    assert len(fitted.projects) == 3 and pdf == b"fit"
    assert len(rendered) <= 4


def test_one_page_fitting_reduces_skills_before_courses_or_projects(monkeypatch):
    current_job = software_job()
    content = generate_local_content(current_job, profile())
    original_projects = [item.name for item in content.projects]
    original_coursework = [item.name for item in content.coursework]
    original_skill_count = len(content.selected_skills)
    attempts = iter(((b"first", 2, 100.0), (b"second", 2, 100.0), (b"final", 1, 90.0)))
    monkeypatch.setattr(
        "app.services.resume_generation._compile_latex_artifact",
        lambda _latex: next(attempts),
    )

    fitted, _, pdf, _ = fit_resume_to_one_page(content, current_job, profile())

    assert pdf == b"final"
    assert len(fitted.selected_skills) == original_skill_count - 2
    assert [item.name for item in fitted.projects] == original_projects
    assert [item.name for item in fitted.coursework] == original_coursework


def test_private_resume_endpoint_rejects_wrong_secret(monkeypatch):
    monkeypatch.setattr("app.main.settings.internal_api_secret", "expected")
    with TestClient(app, headers=security_headers()) as client:
        response = client.get(
            "/api/resume-profile",
            headers={"x-internal-api-secret": "wrong"},
        )
        assert response.status_code == 401


def test_verified_skills_endpoint_exposes_read_only_evidence_registry():
    with TestClient(app, headers=security_headers()) as client:
        response = client.get("/api/resume-profile/verified-skills")
    assert response.status_code == 200, response.text
    groups = response.json()
    assert 2 <= len(groups)
    skills = {
        item["skill"]: item
        for group in groups
        for item in group["items"]
    }
    assert "C++" in skills
    assert skills["C++"]["evidence"]
    assert "x86 Assembly" not in skills


def test_generated_resume_version_keeps_its_original_skill_snapshot():
    init_db()
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        stored_profile = db.query(ResumeProfile).first()
        assert stored_profile is not None
        # A generated version stores an immutable snapshot rather than reading the
        # current master profile every time it is displayed.
        job_id = db.execute(select(Job.id).limit(1)).scalar_one_or_none()
        if job_id is None:
            snapshot_job = Job(
                source_name="snapshot-test", source_url="https://example.com/job",
                company="Example", title="Snapshot test", apply_url="https://example.com/apply",
                raw_data_hash="snapshot-test",
            )
            db.add(snapshot_job)
            db.flush()
            job_id = snapshot_job.id
        original_skills = list(stored_profile.skills_json)
        version = GeneratedResume(
            user_id=stored_profile.user_id,
            job_id=job_id,
            version=9999,
            status="compiled",
            target_role="Snapshot test",
            selected_skills=["C++", "Linux", "Git"],
            skill_categories=[{
                "name": "Languages", "items": ["C++", "Linux", "Git"],
            }],
            job_skill_matches=[{
                "skill": "C++", "category": "Languages", "match_type": "required",
                "score": 30, "reason": "Direct job requirement",
                "evidence": ["Verified skill record"], "job_occurrences": 1,
            }],
            skill_verification={
                "all_verified": True, "verified": ["C++", "Linux", "Git"],
                "removed": [], "registry_size": len(original_skills),
            },
            content_hash="snapshot-test",
        )
        db.add(version)
        db.commit()
        version_id = version.id
        try:
            stored_profile.skills_json = ["Python"]
            db.commit()
            db.expire_all()
            persisted = db.get(GeneratedResume, version_id)
            assert persisted is not None
            assert persisted.selected_skills == ["C++", "Linux", "Git"]
            assert persisted.skill_categories[0]["items"] == ["C++", "Linux", "Git"]
            assert persisted.skill_verification["all_verified"] is True
        finally:
            stored_profile = db.get(ResumeProfile, stored_profile.id)
            if stored_profile is not None:
                stored_profile.skills_json = original_skills
            persisted = db.get(GeneratedResume, version_id)
            if persisted is not None:
                db.delete(persisted)
            db.commit()
