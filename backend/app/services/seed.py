from __future__ import annotations

from copy import deepcopy
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.models import CompanySource, Job, ResumeProfile, TargetCompany, UserProfile
from app.services.resume_generation import (
    CANONICAL_DEGREE,
    CANONICAL_EMAIL,
    CANONICAL_GITHUB,
    CANONICAL_GPA,
    CANONICAL_GRADUATION,
    CANONICAL_INSTITUTION,
    CANONICAL_LINKEDIN,
    CANONICAL_LOCATION,
    CANONICAL_NAME,
    CANONICAL_PHONE,
    CANONICAL_STUDENT_TITLE,
)
from app.services.target_companies import seed_records
from app.services.discovery_orchestration import source_domain, source_group
from app.services.discovery_orchestration import source_domain, source_group
from app.services.discovery_orchestration import source_domain, source_group
from app.sources.company_sources import OFFICIAL_COMPANY_SOURCES
from app.sources.community_sources import COMMUNITY_SOURCES

WATCHLIST = [
    "Amazon",
    "Apple",
    "NXP",
    "Intel",
    "AMD",
    "NVIDIA",
    "Qualcomm",
    "Texas Instruments",
    "Bosch",
    "Honeywell",
    "Rockwell Automation",
    "Siemens",
    "Nokia",
    "Ericsson",
    "Ciena",
    "Cirrus Logic",
    "AMETEK",
    "WindBorne Systems",
    "Garmin",
    "Cisco",
    "Microsoft",
    "Google",
    "Duolingo",
    "Meta",
    "IBM",
    "Oracle",
    "Tesla",
    "Rivian",
    "SpaceX",
    "Astranis",
    "Zoox",
    "Roblox",
    "Anduril",
    "Zipline",
    "GE Vernova",
    "Eaton",
    "Schneider Electric",
    "Continental",
    "Ford",
    "General Motors",
    "John Deere",
    "Caterpillar",
    "Microchip",
    "Analog Devices",
    "Arm",
    "Samsung Semiconductor",
    "SK hynix",
    "Marvell",
    "Broadcom",
    "Infineon",
    "STMicroelectronics",
    "Synopsys",
    "Cadence",
    "FORVIA HELLA",
    "HPE",
    "Hewlett Packard Enterprise",
    "HP",
    "Jabil",
    "Flex",
    "Plexus",
    "Micron",
    "Sanmina",
    "AstraZeneca",
    "Capgemini Engineering",
    # Broad discovery targets.  They remain reference-only until an official
    # adapter/ATS endpoint is configured, so this never fabricates listings.
    "Apple", "Texas Instruments", "Analog Devices", "Applied Materials",
    "Lam Research", "KLA", "ASML", "Lucid", "GE Aerospace", "RTX",
    "Lockheed Martin", "Northrop Grumman", "Blue Origin", "Boston Dynamics",
    "Stripe", "Datadog", "Snowflake", "Confluent", "Palantir", "Uber",
    "Lyft", "DoorDash", "Airbnb", "Reddit", "Pinterest", "LinkedIn",
    "Salesforce", "ServiceNow", "Dell", "Autodesk", "MathWorks", "Bloomberg",
    "Jane Street", "Five Rings", "Hudson River Trading", "Citadel", "IMC",
    "Optiver", "Shopify", "BlackBerry", "Magna", "Celestica", "Thales Canada",
    "Ericsson Canada", "AMD Canada", "Amazon Canada", "Microsoft Canada",
    "Google Canada", "NVIDIA Canada", "Intel Canada", "Qualcomm Canada",
]

PUBLIC_COMPANY_SOURCES = OFFICIAL_COMPANY_SOURCES + [
    {
        "company": "Anduril",
        "source_type": "greenhouse",
        "source_identifier": "andurilindustries",
        "source_url": "https://boards.greenhouse.io/andurilindustries",
    },
    {
        "company": "Astranis",
        "source_type": "greenhouse",
        "source_identifier": "astranis",
        "source_url": "https://boards.greenhouse.io/astranis",
    },
    {
        "company": "Zipline",
        "source_type": "greenhouse",
        "source_identifier": "flyzipline",
        "source_url": "https://boards.greenhouse.io/flyzipline",
    },
    {
        "company": "SpaceX",
        "source_type": "greenhouse",
        "source_identifier": "spacex",
        "source_url": "https://boards.greenhouse.io/spacex",
    },
]

INTERNSHIP_RADAR_PROJECT = {
    "name": "Internship Radar - AI Resume Tailoring Platform",
    "status": "In progress / near completion",
    "technologies": [
        "Next.js", "TypeScript", "FastAPI", "Python", "PostgreSQL",
        "SQLAlchemy", "Pydantic", "OpenAI API", "Jinja2", "LaTeX",
        "Tectonic", "Auth.js", "Git", "Docker", "REST APIs",
        "Backend Development", "Full-Stack Development", "Software Validation",
    ],
    "repository_url": "https://github.com/example-org/internship-radar",
    "live_url": "",
    "is_public": True,
    "is_resume_eligible": True,
    "bullets": [
        "Built a full-stack platform that tracks internship opportunities and generates tailored, ATS-compatible resumes from verified user profile data.",
        "Implemented structured AI generation, validation rules, dynamic Jinja2 and LaTeX templates, and automated PDF compilation for consistent one-page resumes.",
        "Developed authenticated job tracking, resume versioning, PDF preview and download, LaTeX source viewing, and job-specific project selection.",
    ],
}

VERIFIED_RESUME_PROJECTS = [
    {
        "name": "Autonomous Lab Rover",
        "technologies": [
            "C", "C++", "UART", "PWM", "Embedded Systems", "Robotics",
            "Microcontrollers", "Hardware/Software Integration", "Hardware Debugging",
        ],
        "repository_url": "https://github.com/example-candidate/autonomous-lab-rover",
        "is_public": True,
        "is_resume_eligible": True,
        "bullets": [
            "Integrated two microcontrollers with UART communication and PWM motor control to coordinate a small autonomous laboratory rover.",
            "Developed embedded control, sensor processing, actuator coordination, and repeatable hardware tests across a modular prototype.",
        ],
    },
    {
        "name": "Embedded Telemetry Gateway",
        "technologies": [
            "C", "FreeRTOS", "GPIO", "ADC", "PWM", "Interrupts",
            "Microcontrollers", "Mutexes", "Semaphores", "Queues",
            "Concurrent Programming", "Multithreaded Programming", "Software Debugging",
            "Software Validation",
        ],
        "repository_url": "https://github.com/example-candidate/embedded-telemetry-gateway",
        "is_public": True,
        "is_resume_eligible": True,
        "bullets": [
            "Programmed an event-driven telemetry gateway in C using GPIO, ADC, PWM, interrupts, and FreeRTOS task coordination.",
            "Tested concurrent tasks, queues, semaphores, timing, and peripheral behavior with reproducible board-level validation procedures.",
        ],
    },
    {
        "name": "FPGA Signal Processor",
        "technologies": [
            "Verilog", "SystemVerilog", "FPGA", "FPGA Design",
            "Digital Logic", "UART", "PWM", "Hardware/Software Integration",
        ],
        "repository_url": "https://github.com/example-candidate/fpga-signal-processor",
        "is_public": True,
        "is_resume_eligible": True,
        "bullets": [
            "Designed Verilog and SystemVerilog RTL modules, finite-state machines, UART interfaces, and streaming signal-processing stages.",
            "Validated digital designs with self-checking testbenches and waveform analysis before integrating the complete FPGA processing pipeline.",
        ],
    },
    {
        "name": "Route Optimization Engine",
        "technologies": [
            "C++", "Object-Oriented Programming", "Graph Algorithms",
            "Data Structures", "Algorithms", "Testing",
        ],
        "repository_url": "https://github.com/example-candidate/route-optimization-engine",
        "is_public": True,
        "is_resume_eligible": True,
        "bullets": [
            "Developed a modular C++ graph engine representing locations, edges, costs, and valid traversal paths through object-oriented components.",
            "Implemented route search and path validation with deterministic tests for graph updates, unreachable nodes, and competing path costs.",
        ],
    },
    {
        "name": "Environmental Sensor Dashboard",
        "technologies": [
            "Python", "Flask", "REST APIs", "MySQL", "Linux", "I2C",
            "Raspberry Pi", "Hardware/Software Integration", "Software Validation",
        ],
        "repository_url": "https://github.com/example-candidate/environmental-sensor-dashboard",
        "is_public": True,
        "is_resume_eligible": True,
        "bullets": [
            "Built a Linux-based environmental monitor that reads particulate sensors and exposes validated measurements through a Flask REST API.",
            "Implemented SQL logging, browser visualization, device status output, and threshold-based controls with automated validation fixtures.",
        ],
    },
    {
        "name": "Market Simulation Engine",
        "technologies": [
            "C++", "Object-Oriented Programming", "Data Structures",
            "Algorithms", "File I/O",
        ],
        "repository_url": "https://github.com/example-candidate/market-simulation-engine",
        "is_public": True,
        "is_resume_eligible": True,
        "bullets": [
            "Implemented a C++ event simulator that matches synthetic orders using price-time priority and per-symbol priority queues.",
            "Designed object-oriented event processing, file-based fixtures, and terminal reporting for deterministic, repeatable market-behavior experiments and analysis.",
        ],
    },
]

VERIFIED_PROJECT_SKILLS = sorted({
    technology
    for project in VERIFIED_RESUME_PROJECTS
    for technology in project["technologies"]
})

VERIFIED_COURSES = [
    {
        "name": "Data Structures with Python",
        "institution": "Example Online University",
        "issued": "2025",
        "areas": ["Python", "Data Structures", "Software Engineering"],
        "priority": "normal",
    },
    {
        "name": "Building Web APIs with Python",
        "institution": "Example Online University",
        "issued": "2025",
        "areas": ["Python", "Web Data", "APIs", "Backend"],
        "priority": "normal",
    },
    {
        "name": "Python Programming Fundamentals",
        "institution": "Example Online University",
        "issued": "2024",
        "areas": ["Python Fundamentals"],
        "priority": "low",
    },
]


def enrich_resume_profile(db: Session) -> None:
    profile = db.scalar(select(ResumeProfile).where(ResumeProfile.user_id == settings.effective_primary_user_id).limit(1))
    if profile is None:
        return
    profile.user_id = settings.effective_primary_user_id
    profile.full_name = CANONICAL_NAME
    profile.email = CANONICAL_EMAIL
    profile.phone = CANONICAL_PHONE
    profile.location = CANONICAL_LOCATION
    profile.linkedin_url = CANONICAL_LINKEDIN
    profile.github_url = CANONICAL_GITHUB
    profile.headline = CANONICAL_STUDENT_TITLE

    education = deepcopy(profile.education_json or [])
    current_education = education[0] if education and isinstance(education[0], dict) else {}
    canonical_education = {
        **current_education,
        "institution": CANONICAL_INSTITUTION,
        "degree": CANONICAL_DEGREE,
        "location": CANONICAL_LOCATION,
        "graduation": CANONICAL_GRADUATION,
        "gpa": CANONICAL_GPA,
        "coursework": list(current_education.get("coursework") or []),
    }
    if education:
        education[0] = canonical_education
    else:
        education.append(canonical_education)
    profile.education_json = education
    flag_modified(profile, "education_json")

    skills = list(profile.skills_json or [])
    for skill in [*INTERNSHIP_RADAR_PROJECT["technologies"], *VERIFIED_PROJECT_SKILLS]:
        if skill not in skills:
            skills.append(skill)
    profile.skills_json = skills

    verified_languages = [
        "Spanish — Native",
        "English — Professional",
        "Portuguese — Basic",
    ]
    languages = list(profile.languages_json or [])
    existing_languages = {
        str(item).split("—", 1)[0].strip().lower()
        for item in languages
    }
    for language in verified_languages:
        name = language.split("—", 1)[0].strip().lower()
        if name not in existing_languages:
            languages.append(language)
    profile.languages_json = languages
    flag_modified(profile, "languages_json")

    projects = deepcopy(profile.projects_json or [])
    radar = next(
        (
            item for item in projects
            if item.get("name") == INTERNSHIP_RADAR_PROJECT["name"]
        ),
        None,
    )
    if radar is None:
        projects.append(deepcopy(INTERNSHIP_RADAR_PROJECT))
    else:
        radar["repository_url"] = INTERNSHIP_RADAR_PROJECT["repository_url"]
        radar["live_url"] = INTERNSHIP_RADAR_PROJECT["live_url"]
        radar["is_public"] = INTERNSHIP_RADAR_PROJECT["is_public"]
        radar["is_resume_eligible"] = INTERNSHIP_RADAR_PROJECT["is_resume_eligible"]
        radar["technologies"] = deepcopy(INTERNSHIP_RADAR_PROJECT["technologies"])
        radar["bullets"] = deepcopy(INTERNSHIP_RADAR_PROJECT["bullets"])

    project_by_name = {
        item.get("name"): item
        for item in projects
        if isinstance(item, dict) and item.get("name")
    }
    for verified_project in VERIFIED_RESUME_PROJECTS:
        existing = project_by_name.get(verified_project["name"])
        if existing is None:
            projects.append(deepcopy(verified_project))
        else:
            existing.update(deepcopy(verified_project))
    verified_names = {
        INTERNSHIP_RADAR_PROJECT["name"],
        *(project["name"] for project in VERIFIED_RESUME_PROJECTS),
    }
    for project in projects:
        if not isinstance(project, dict) or project.get("name") in verified_names:
            continue
        if len(project.get("bullets") or []) < 2:
            project["is_resume_eligible"] = False
    profile.projects_json = projects
    flag_modified(profile, "projects_json")

    existing_courses = {
        item.get("name") for item in profile.coursework_json or [] if isinstance(item, dict)
    }
    courses = deepcopy(profile.coursework_json or [])
    courses.extend(
        deepcopy(course) for course in VERIFIED_COURSES
        if course["name"] not in existing_courses
    )
    profile.coursework_json = courses
    flag_modified(profile, "coursework_json")


def seed_profile_and_sources(db: Session) -> None:
    db.info['owner_user_id'] = settings.effective_primary_user_id
    db.info['owner_user_id'] = settings.effective_primary_user_id
    db.info['owner_user_id'] = settings.effective_primary_user_id
    existing_targets = {
        name.lower()
        for name in db.scalars(select(TargetCompany.company_name))
    }
    for target_data in seed_records():
        if target_data["company_name"].lower() not in existing_targets:
            db.add(TargetCompany(**target_data))
    base_profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == settings.effective_primary_user_id).limit(1))
    if base_profile is None:
        db.add(
            UserProfile(
                full_name="Alex Rivera",
                degree="B.S. in Computer Engineering",
                university="Example Institute of Technology",
                graduation_year=2029,
                graduation_date=date(2029, 5, 31),
                degree_level_current="BACHELORS",
                degree_status="IN_PROGRESS",
                expected_graduation_date=date(2029, 5, 31),
                degree_field="Computer Engineering",
                veteran_status="NOT_VETERAN",
                military_status="NONE",
                military_spouse=False,
                disability_status="NO_DISABILITY",
                current_service_member=False,
                gpa=3.7,
                gpa_scale=4.0,
                nationality="Mexican",
                citizenship_country="Mexico",
                visas=[],
                work_authorizations={
                    "Mexico": "Citizen / authorized",
                    "United States": "No current work authorization",
                    "Canada": "No current work authorization",
                },
                work_authorized_countries=["Mexico"],
                us_work_authorized=False,
                requires_us_employment_sponsorship=True,
                willing_to_relocate=True,
                preferred_locations=[
                    "Mexico",
                    "United States (sponsorship risk)",
                    "Canada (permit risk)",
                    "Remote",
                ],
                preferred_roles=[
                    "Software Development Engineering",
                    "Firmware / Embedded",
                    "FPGA / RTL / Digital Design",
                    "Hardware Test / Validation",
                    "Robotics / Controls",
                    "Computer Vision",
                    "Linux Systems",
                ],
                skills=[
                    "C",
                    "C++",
                    "Python",
                    "TypeScript",
                    "Linux",
                    "Git",
                    "Embedded Systems",
                    "Firmware",
                    "RTOS",
                    "FPGA",
                    "Verilog",
                    "SystemVerilog",
                    "Digital Design",
                    "Robotics",
                    "Controls",
                    "Electronics",
                    "Oscilloscope",
                    "Testing",
                    "SQL",
                    "Docker",
                    "FastAPI",
                ],
                projects=[
                    {
                        "name": "Autonomous lab rover",
                        "details": "C++, sensor fusion, motor control, and validation fixtures.",
                    },
                    {
                        "name": "FPGA signal processor",
                        "details": "Verilog RTL, simulation, self-checking testbenches, and streaming interfaces.",
                    },
                    {
                        "name": "Embedded telemetry gateway",
                        "details": "C, RTOS tasks, serial protocols, Linux tooling, and hardware debugging.",
                    },
                ],
                education_notes="Fictional demo profile. Open to relocation; internships must remain compatible with degree progress.",
                email_notifications=True,
                notification_email=settings.notification_email,
                priority_email_alerts=True,
                major_company_email_alerts=False,
                deadline_alerts=False,
                daily_digest=False,
                application_follow_up_alerts=False,
                email_minimum_score=80,
            )
        )
    else:
        base_profile.degree_level_current = "BACHELORS"
        base_profile.degree_status = "IN_PROGRESS"
        base_profile.expected_graduation_date = date(2029, 5, 31)
        base_profile.degree_field = "Computer Engineering"
        base_profile.veteran_status = "NOT_VETERAN"
        base_profile.military_status = "NONE"
        base_profile.military_spouse = False
        base_profile.disability_status = "NO_DISABILITY"
        base_profile.current_service_member = False
        base_profile.email_notifications = True
        base_profile.notification_email = settings.notification_email
        base_profile.priority_email_alerts = True
        base_profile.major_company_email_alerts = False
        base_profile.deadline_alerts = False
        base_profile.daily_digest = False
        base_profile.application_follow_up_alerts = False

    db.flush()
    if db.scalar(select(ResumeProfile.id).limit(1)) is None:
        base_profile = db.scalar(select(UserProfile).where(UserProfile.owner_user_id == settings.effective_primary_user_id).limit(1))
        if base_profile:
            db.add(
                ResumeProfile(
                    user_id=settings.effective_primary_user_id,
                    full_name=base_profile.full_name,
                    email=settings.resume_email,
                    location="Mexico",
                    headline=base_profile.degree,
                    summary=base_profile.education_notes,
                    education_json=[
                        {
                            "institution": base_profile.university,
                            "degree": base_profile.degree,
                            "location": "Mexico",
                            "graduation": str(base_profile.graduation_year),
                            "gpa": f"{base_profile.gpa}/{base_profile.gpa_scale}",
                            "coursework": [],
                        }
                    ],
                    skills_json=base_profile.skills,
                    experience_json=[],
                    projects_json=base_profile.projects,
                    coursework_json=[],
                    certifications_json=[],
                    languages_json=[
                        "Spanish — Native",
                        "English — Professional",
                        "Portuguese — Basic",
                    ],
                    forbidden_claims_json=[
                        "C#",
                        ".NET",
                        "MCP",
                        "AWS certification",
                        "Azure certification",
                        "OCI certification",
                    ],
                )
            )

    # SessionLocal disables autoflush. Make a newly created ResumeProfile visible
    # to enrich_resume_profile() during this same first-run transaction.
    db.flush()

    local_source = db.scalar(
        select(CompanySource).where(CompanySource.source_type == "local_json").limit(1)
    )
    if local_source is None:
        db.add(
            CompanySource(
                company="MVP test feed",
                source_type="local_json",
                source_identifier="data/test_jobs.json",
                source_url="local://data/test_jobs.json",
                enabled=settings.demo_feed_enabled,
            )
        )
    else:
        local_source.enabled = settings.demo_feed_enabled
    existing_watchlist = {
        company.lower()
        for company in db.scalars(
            select(CompanySource.company).where(CompanySource.source_type == "manual_watchlist")
        )
    }
    public_company_names = {
        source["company"].lower() for source in PUBLIC_COMPANY_SOURCES
    }
    for company in WATCHLIST:
        if company.lower() in public_company_names:
            continue
        if company.lower() not in existing_watchlist:
            db.add(
                CompanySource(
                    company=company,
                    source_type="manual_watchlist",
                    source_identifier=company.lower().replace(" ", "-"),
                    source_url="https://example.com/configure-official-careers-url",
                    enabled=False,
                    last_status="Needs official URL",
                )
            )
    for source_data in PUBLIC_COMPANY_SOURCES:
        source_data = {
            "registry_type": "OFFICIAL_ATS" if source_data["source_type"] in {
                "greenhouse", "lever", "workday", "smartrecruiters",
                "oracle_recruiting", "amazon_jobs",
            } else "OFFICIAL_COMPANY",
            "priority": 90,
            "base_priority": 90,
            "trust_level": "PRIMARY",
            "refresh_frequency": "daily",
            "supports_structured_data": source_data["source_type"] not in {"official_careers"},
            "source_confidence_score": 95 if source_data["source_type"] != "official_careers" else 100,
            **source_data,
        }
        stale_sources = list(
            db.scalars(
                select(CompanySource).where(
                    CompanySource.company == source_data["company"],
                    CompanySource.source_type != "manual_watchlist",
                    or_(
                        CompanySource.source_type != source_data["source_type"],
                        CompanySource.source_identifier != source_data["source_identifier"],
                    ),
                )
            )
        )
        for stale_source in stale_sources:
            stale_source.enabled = False
            stale_source.last_status = "Replaced"
            stale_source.last_error = "Replaced by the current official careers source."
        source = db.scalar(
            select(CompanySource).where(
                CompanySource.source_type == source_data["source_type"],
                CompanySource.source_identifier == source_data["source_identifier"],
            )
        )
        if source is None:
            source = db.scalar(
                select(CompanySource).where(
                    CompanySource.company == source_data["company"],
                    CompanySource.source_type == "manual_watchlist",
                )
            )
        if source is None:
            source = CompanySource(**source_data)
            db.add(source)
        else:
            for key, value in source_data.items():
                setattr(source, key, value)
        source.enabled = True
        if source.last_status == "Needs official URL":
            source.last_status = "Never"
    for source_data in COMMUNITY_SOURCES:
        source = db.scalar(
            select(CompanySource).where(
                CompanySource.source_type == source_data["source_type"],
                CompanySource.source_identifier == source_data["source_identifier"],
            )
        )
        if source is None:
            db.add(CompanySource(**source_data, enabled=True, last_status="Never"))
        else:
            for key, value in source_data.items():
                setattr(source, key, value)
    embedded_source = db.scalar(
        select(CompanySource).where(CompanySource.source_type == "embedded_jobs").limit(1)
    )
    if embedded_source is None:
        db.add(
            CompanySource(
                company="EmbeddedJobs",
                source_type="embedded_jobs",
                source_identifier="internship-embedded-systems-jobs",
                source_url="https://embedded.jobs",
                enabled=True,
                last_status="Never",
            )
        )

    demo_jobs = list(
        db.scalars(
            select(Job).where(
                or_(Job.source_name == "Local JSON", Job.external_id.like("demo-%"))
            )
        )
    )
    for job in demo_jobs:
        job.discovery_status = "demo"
        job.is_priority_alert = False
        job.priority_alerted_at = None
        if not settings.demo_feed_enabled:
            job.official_apply_url = None
            job.official_status = "unknown"
            job.verification_status = "unverified"
            job.verification_method = "demo_fixture"
            job.status_reason = (
                "Demo fixture only. This record has no real application page."
            )
            if job.analysis:
                job.analysis.recommendation = "Needs Verification"
    enrich_resume_profile(db)
    db.commit()


def ensure_santiago_resume_projects(profile: ResumeProfile) -> bool:
    """Private per-person reconciliation is not distributed in the showcase."""
    return False
