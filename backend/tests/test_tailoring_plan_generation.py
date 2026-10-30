from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services import resume_generation
from app.services.resume_generation import (
    CANONICAL_EMAIL,
    classify_job,
    generate_local_content,
    _scoped_tailoring_plan,
    weighted_role_categories,
)
from app.services.seed import (
    INTERNSHIP_RADAR_PROJECT,
    VERIFIED_COURSES,
    VERIFIED_PROJECT_SKILLS,
    VERIFIED_RESUME_PROJECTS,
)
from app.services.tailoring_plan import TailoringPlan, build_tailoring_plan, decide_resume_content, job_content_hash


def santiago_profile(user_id: str = "santiago") -> SimpleNamespace:
    """A scoped regression profile containing Santiago's verified project evidence."""
    projects = [deepcopy(INTERNSHIP_RADAR_PROJECT), *deepcopy(VERIFIED_RESUME_PROJECTS)]
    return SimpleNamespace(
        user_id=user_id,
        full_name="Alex Rivera",
        email=CANONICAL_EMAIL,
        phone="+52 33 0000 0000",
        location="Zapopan, Jalisco, Mexico",
        linkedin_url="https://www.linkedin.com/in/example-candidate/",
        github_url="https://github.com/example-candidate",
        headline="Robotics and Digital Systems Engineering Student",
        summary="Verified engineering profile.",
        education_json=[{
            "institution": "Tecnologico de Monterrey",
            "degree": "B.S. in Robotics and Digital Systems Engineering",
            "location": "Zapopan, Jalisco, Mexico",
            "graduation": "Expected Graduation: June 2028",
            "gpa": "93.05/100",
        }],
        skills_json=sorted({
            *INTERNSHIP_RADAR_PROJECT["technologies"], *VERIFIED_PROJECT_SKILLS,
            "Testing", "Debugging", "Linux", "REST APIs", "Python", "C", "C++",
        }),
        experience_json=[],
        projects_json=projects,
        coursework_json=deepcopy(VERIFIED_COURSES),
        certifications_json=[],
        languages_json=["Spanish - Native", "English - Fluent", "German - Basic"],
        forbidden_claims_json=[],
    )


def scoped_job(
    title: str,
    requirements: str,
    *,
    description: str = "",
    preferred: str = "",
    area: str = "Engineering",
    user_id: str = "santiago",
    job_id: int = 901,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=job_id,
        owner_user_id=user_id,
        title=title,
        company="Google",
        area=area,
        requirements=requirements,
        preferred_qualifications=preferred,
        description=description,
        analysis=None,
        application_type="STANDARD_JOB",
        resume_target="",
    )


def project_names(content):
    return [project.name for project in content.projects]


def plan_decisions(content):
    return content.tailoring_plan["resume_decisions"]


def test_santiago_regression_plans_differ_for_security_solutions_embedded_and_fpga():
    profile = santiago_profile()
    security = generate_local_content(scoped_job(
        "Security Consultant Intern",
        "Python, RESTful APIs, Linux, testing, and debugging are required. "
        "Penetration Testing, Malware Analysis, SIEM, SOC, and Incident Response preferred.",
        description="Help customers investigate security issues and validate secure integrations.",
    ), profile)
    solutions = generate_local_content(scoped_job(
        "Customer and Partner Solutions Engineering Intern",
        "Python, REST APIs, FastAPI, Flask, integration, and debugging are required.",
        description="Build and troubleshoot partner integrations and backend services.",
    ), profile)
    embedded = generate_local_content(scoped_job(
        "Embedded Software Engineering Intern",
        "C, C++, FreeRTOS, microcontrollers, UART, PWM, and hardware/software integration are required.",
        description="Develop, test, and debug real-time firmware for embedded systems.",
    ), profile)
    fpga = generate_local_content(scoped_job(
        "FPGA Design Intern",
        "FPGA, Verilog, SystemVerilog, digital design, RTL, simulation, and testing are required.",
        description="Design and validate RTL modules for programmable logic.",
    ), profile)

    assert project_names(security) != project_names(embedded)
    assert "Internship Radar - AI Resume Tailoring Platform" in project_names(security)
    assert "SkiliAir Air Quality Monitoring System" in project_names(security)
    assert "Internship Radar - AI Resume Tailoring Platform" in project_names(solutions)
    assert "SkiliAir Air Quality Monitoring System" in project_names(solutions)
    assert {"FreeRTOS Event-Driven System", "MATT Web-Controlled Writing Robot", "Intel MAX 10 Robotic Arm Controller"} <= set(project_names(embedded))
    assert project_names(fpga)[0] == "Intel MAX 10 Robotic Arm Controller"
    assert {"Verilog", "SystemVerilog", "FPGA"} <= set(fpga.selected_skills)

    security_decisions = plan_decisions(security)
    assert {"Penetration Testing", "Malware Analysis", "SIEM", "SOC", "Incident Response"} <= set(security_decisions["missing_requirements"])
    assert not {"Penetration Testing", "Malware Analysis", "SIEM", "SOC", "Incident Response"} & set(security.selected_skills)


def test_google_security_consultant_keeps_overlapping_security_roles_and_truthful_resume():
    profile = santiago_profile()
    job = scoped_job(
        "Google Security Consultant Intern",
        "Python, RESTful APIs, Linux, testing, and debugging are required. "
        "Penetration Testing, Malware Analysis, SIEM, SOC, and Incident Response preferred.",
        description="Support customers with system security reviews and validate secure integrations.",
    )

    content = generate_local_content(job, profile)
    plan = content.tailoring_plan
    expected_codes = {
        "SECURITY_CONSULTING", "SECURITY_ENGINEERING", "CYBERSECURITY", "SYSTEM_SECURITY",
    }

    assert classify_job(job) == "Security / Consulting"
    assert expected_codes <= set(weighted_role_categories(job))
    assert expected_codes <= set(plan["role_category_codes"])
    assert plan["role_categories"][:4] == [
        "Security Consulting", "Security Engineering", "Cybersecurity", "System Security",
    ]
    assert content.classification == "Security / Consulting"
    assert "Security Consulting" in content.headline
    assert "Security Consulting role" in content.summary
    assert "Software Engineering role" not in content.summary
    assert {"Internship Radar - AI Resume Tailoring Platform", "SkiliAir Air Quality Monitoring System"} <= set(project_names(content))
    assert not {"Penetration Testing", "Malware Analysis", "SIEM", "SOC", "Incident Response"} & set(content.selected_skills)


def test_role_aware_project_evidence_changes_rankings_without_project_templates():
    profile = santiago_profile()
    security = generate_local_content(scoped_job(
        "Google Security Consultant Intern",
        "Python, RESTful APIs, Linux, testing, and debugging are required.",
        description="Support system security reviews and validate secure integrations.",
    ), profile)
    security_scores = plan_decisions(security)["selected_project_scores"]
    assert security_scores["Internship Radar - AI Resume Tailoring Platform"] > security_scores["Königsberg Graph Game"]
    assert security_scores["SkiliAir Air Quality Monitoring System"] > security_scores["Königsberg Graph Game"]
    assert "Role evidence: backend or API evidence." in " ".join(
        plan_decisions(security)["selected_project_reasons"]["Internship Radar - AI Resume Tailoring Platform"]
    )

    embedded = generate_local_content(scoped_job(
        "Intel Embedded Intern",
        "C, C++, FreeRTOS, microcontrollers, UART, PWM, and hardware/software integration are required.",
        description="Develop, test, and debug real-time firmware for embedded systems.",
    ), profile)
    assert {"FreeRTOS Event-Driven System", "MATT Web-Controlled Writing Robot", "Intel MAX 10 Robotic Arm Controller"} <= set(project_names(embedded)[:3])
    assert "Internship Radar - AI Resume Tailoring Platform" not in project_names(embedded)[:3]

    fpga = generate_local_content(scoped_job(
        "FPGA Intern",
        "FPGA, Verilog, SystemVerilog, digital design, RTL, simulation, and testing are required.",
        description="Design and validate RTL modules for programmable logic.",
    ), profile)
    assert project_names(fpga)[0] == "Intel MAX 10 Robotic Arm Controller"

    software = generate_local_content(scoped_job(
        "Software Engineering Intern",
        "C++, algorithms, data structures, backend, software architecture, testing, and debugging are required.",
        description="Build reliable software systems.",
    ), profile)
    assert project_names(software)[:2] == ["Königsberg Graph Game", "Stock Exchange Matching Engine"]


def test_automotive_mcu_npi_uses_embedded_role_and_projects_instead_of_graph_game():
    job = scoped_job(
        "INTERN - Automotive MCU NPI",
        "C, C++, microcontrollers, SPI, I2C, UART, Ethernet, CAN, LIN, PWM, testing, and validation.",
        area="Automotive MCU / Embedded Systems / NPI",
        description=(
            "Support automotive microcontroller new product introduction. Prepare technical "
            "documentation and code examples, and test software stacks, operating systems, "
            "and device drivers for microcontroller peripherals."
        ),
    )

    assert classify_job(job) == "Embedded / Firmware"
    assert weighted_role_categories(job)["EMBEDDED"] > weighted_role_categories(job).get("SOFTWARE_ENGINEERING", 0)

    content = generate_local_content(job, santiago_profile())
    decisions = plan_decisions(content)
    assert decisions["primary_role_category"] == "Embedded / Firmware"
    assert "Embedded / Firmware" in content.tailoring_plan["role_categories"]
    assert "Königsberg Graph Game" not in project_names(content)
    assert any(
        term in " ".join(project_names(content)).lower()
        for term in ("motor", "freertos", "matt", "kl25z", "ble", "embedded")
    )

    # Existing immutable snapshots with the previous classification are not
    # reused for a new generation even though the job text/hash is unchanged.
    stale_plan = resume_generation.build_tailoring_plan(job, santiago_profile(), owner_user_id="santiago")
    stale_plan.role_categories = ["Software Engineering"]
    refreshed = _scoped_tailoring_plan(
        job, santiago_profile(), project_limit=4, existing_plan=stale_plan,
    )
    assert refreshed is not None
    assert "Embedded / Firmware" in refreshed.role_categories
    assert refreshed.resume_decisions.primary_role_category == "Embedded / Firmware"


def test_generated_resume_uses_plan_not_legacy_project_priority_lists(monkeypatch):
    profile = santiago_profile()
    job = scoped_job(
        "FPGA Design Intern",
        "FPGA, Verilog, SystemVerilog, digital design, and PWM are required.",
    )
    monkeypatch.setattr(resume_generation, "PROJECT_PRIORITIES", {"FPGA / Digital Design": ["Not candidate evidence"]})

    content = generate_local_content(job, profile)

    assert content.tailoring_plan["resume_decisions"]["status"] == "PLANNED"
    assert project_names(content)[0] == "Intel MAX 10 Robotic Arm Controller"
    assert plan_decisions(content)["selected_projects"] == project_names(content)


def test_asic_and_software_decisions_remain_role_specific_after_layout_adjustment(monkeypatch):
    profile = santiago_profile()
    asic_job = scoped_job(
        "Amazon ASIC Engineer Intern - Annapurna Labs",
        "Verilog, SystemVerilog, FPGA, Digital Design, RTL, hardware validation, embedded systems, C, and C++ are required.",
        description="Design, simulate, validate, and debug RTL and ASIC hardware.",
        job_id=903,
    )
    asic_job.company = "Amazon"
    software_job = scoped_job(
        "Software Engineering Intern",
        "Python, C++, algorithms, data structures, backend systems, testing, and debugging are required.",
        description="Build and test reliable software systems.",
        job_id=904,
    )

    asic = generate_local_content(asic_job, profile)
    software = generate_local_content(software_job, profile)

    assert classify_job(asic_job) == "FPGA / Digital Design"
    assert project_names(asic)[0] == "Intel MAX 10 Robotic Arm Controller"
    assert {"Verilog", "SystemVerilog", "FPGA", "Digital Logic", "C", "C++"} <= set(asic.selected_skills)
    assert {"Python", "C++", "Algorithms", "Data Structures"} <= set(software.selected_skills)
    assert plan_decisions(asic)["selected_projects"] == project_names(asic)
    assert plan_decisions(asic)["selected_skills"] == asic.selected_skills

    usages = iter((96.0, 90.0))
    monkeypatch.setattr(
        resume_generation,
        "_compile_latex_artifact",
        lambda _: (b"pdf", 1, next(usages)),
    )
    fitted, _, _, _ = resume_generation.fit_resume_to_one_page(asic, asic_job, profile)

    assert plan_decisions(fitted)["selected_skills"] == fitted.selected_skills
    assert plan_decisions(fitted)["selected_projects"] == project_names(fitted)
    resume_generation.validate_generated_resume(fitted, profile, asic_job)


def test_plan_snapshot_is_immutable_when_a_later_resume_is_generated():
    profile = santiago_profile()
    software = generate_local_content(scoped_job(
        "Solutions Engineering Intern", "Python, REST APIs, FastAPI, Flask, and debugging are required."
    ), profile)
    original_snapshot = deepcopy(software.tailoring_plan)

    generate_local_content(scoped_job(
        "Embedded Intern", "C, FreeRTOS, UART, PWM, and microcontrollers are required."
    ), profile)

    assert software.tailoring_plan == original_snapshot
    assert plan_decisions(software)["selected_projects"] == project_names(software)


def test_sequential_resume_generation_is_isolated_by_job_and_plan_snapshot():
    profile = santiago_profile()
    security_job = scoped_job(
        "Google Security Consultant Intern",
        "Python, RESTful APIs, Linux, testing, and debugging are required.",
        description="Support customers with system security reviews and secure integrations.",
        job_id=901,
    )
    software_job = scoped_job(
        "Google Software Engineering Intern BS Summer 2027",
        "C++, algorithms, data structures, backend systems, testing, and debugging are required.",
        description="Build and test reliable software systems, including secure coding and security reviews.",
        job_id=902,
    )

    security_resume = generate_local_content(security_job, profile)
    security_snapshot = deepcopy(security_resume.tailoring_plan)
    software_resume = generate_local_content(software_job, profile)

    assert security_resume.tailoring_plan["job_id"] == security_job.id
    assert software_resume.tailoring_plan["job_id"] == software_job.id
    assert security_resume.tailoring_plan == security_snapshot
    assert "Security Consulting" in security_resume.headline
    assert plan_decisions(security_resume)["primary_role_category"] == "Security Consulting"
    assert plan_decisions(software_resume)["primary_role_category"] == "Software Engineering"
    assert "Software Engineering" in software_resume.headline
    assert "Security Consulting" not in software_resume.headline
    assert "Cybersecurity" not in software_resume.headline
    assert "For this Software Engineering role" in software_resume.summary
    assert "Security Consulting role" not in software_resume.summary
    assert "Cybersecurity role" not in software_resume.summary
    assert software_resume.tailoring_trace["classification"] == "Software Engineering"

    stale_security_plan = decide_resume_content(
        build_tailoring_plan(security_job, profile, owner_user_id=profile.user_id),
        profile,
    )
    regenerated = generate_local_content(software_job, profile, tailoring_plan=stale_security_plan)
    assert regenerated.tailoring_plan["job_id"] == software_job.id
    assert regenerated.tailoring_plan["job_content_hash"] == job_content_hash(software_job)
    assert "Security Consulting" not in regenerated.headline


def test_job_b_always_builds_its_own_plan_after_generating_job_a():
    profile = santiago_profile()
    job_a = scoped_job(
        "Security Consultant Intern",
        "Python, Linux, RESTful APIs, testing, and debugging are required.",
        description="Review secure system integrations.",
        job_id=1201,
    )
    job_b = scoped_job(
        "Software Engineering Intern",
        "C++, Python, algorithms, data structures, and backend systems are required.",
        description="Develop and test reliable software services.",
        job_id=1202,
    )

    resume_a = generate_local_content(job_a, profile)
    resume_b = generate_local_content(job_b, profile, tailoring_plan=TailoringPlan.model_validate(resume_a.tailoring_plan))

    assert resume_a.tailoring_plan["job_id"] == job_a.id
    assert resume_b.tailoring_plan["job_id"] == job_b.id
    assert resume_b.tailoring_plan["job_content_hash"] == job_content_hash(job_b)
    assert "Security Consulting" not in resume_b.headline


def test_five_rings_link_plan_is_bound_to_current_job_and_requirements():
    profile = santiago_profile()
    prior_job = scoped_job("Embedded Intern", "C, FreeRTOS, UART, and PWM required.", job_id=1301)
    generate_local_content(prior_job, profile)
    link = scoped_job(
        "LINK 2027: Software Development Intensive Program",
        "C++, Python, Linux, networking, distributed systems, C++23, and automated trading systems.",
        description="Five Rings program for software development and automated trading systems.",
        job_id=1302,
    )
    link.company = "Five Rings"

    resume = generate_local_content(link, profile)
    plan = resume.tailoring_plan

    assert plan["job_id"] == link.id
    assert plan["owner_user_id"] == profile.user_id
    assert plan["job_content_hash"] == job_content_hash(link)
    normalized = {item["normalized_requirement"] for item in plan["normalized_requirements"]}
    assert {
        "C++", "Python", "Linux", "Networking", "Distributed Systems",
        "C++23", "Automated Trading Systems",
    } <= normalized
    assert set(resume.selected_skills) <= set(profile.skills_json)
    missing = set(plan["resume_decisions"]["missing_requirements"])
    assert {"Networking", "Distributed Systems", "C++23", "Automated Trading Systems"} <= missing


def test_changed_job_content_invalidates_the_old_plan_but_keeps_the_old_snapshot_immutable():
    profile = santiago_profile()
    job = scoped_job(
        "Software Engineering Intern",
        "C++, Python, algorithms, and testing are required.",
        description="Develop software services.",
        job_id=1401,
    )
    original = generate_local_content(job, profile)
    original_snapshot = deepcopy(original.tailoring_plan)
    stale_plan = TailoringPlan.model_validate(original_snapshot)
    job.description = "Develop distributed systems using Linux, networking, and C++23."

    regenerated = generate_local_content(job, profile, tailoring_plan=stale_plan)

    assert original.tailoring_plan == original_snapshot
    assert regenerated.tailoring_plan["job_id"] == job.id
    assert regenerated.tailoring_plan["job_content_hash"] != original_snapshot["job_content_hash"]


def test_another_users_plan_is_rebuilt_from_the_current_users_evidence():
    alpha = santiago_profile("alpha")
    beta = santiago_profile("beta")
    beta.skills_json = ["C", "C++", "FreeRTOS", "UART", "PWM", "Microcontrollers", "Testing", "Debugging"]
    beta.projects_json = [project for project in beta.projects_json if project["name"] in {
        "FreeRTOS Event-Driven System", "MATT Web-Controlled Writing Robot",
    }]
    alpha_job = scoped_job("Backend Intern", "Python and REST APIs required.", user_id="alpha", job_id=1501)
    beta_job = scoped_job("Firmware Intern", "C, FreeRTOS, UART, and PWM required.", user_id="beta", job_id=1502)
    alpha_plan = TailoringPlan.model_validate(generate_local_content(alpha_job, alpha).tailoring_plan)

    beta_resume = generate_local_content(beta_job, beta, tailoring_plan=alpha_plan)

    assert beta_resume.tailoring_plan["owner_user_id"] == "beta"
    assert beta_resume.tailoring_plan["job_id"] == beta_job.id
    assert "Python" not in beta_resume.selected_skills


def test_planned_resume_never_uses_another_users_evidence():
    alpha = santiago_profile("alpha")
    beta = santiago_profile("beta")
    beta.projects_json = [project for project in beta.projects_json if project["name"] in {
        "FreeRTOS Event-Driven System", "MATT Web-Controlled Writing Robot",
    }]
    beta.skills_json = ["C", "C++", "FreeRTOS", "GPIO", "PWM", "Microcontrollers", "Testing", "Debugging", "UART"]
    alpha_resume = generate_local_content(scoped_job(
        "Solutions Intern", "Python, REST APIs, FastAPI, Flask, and debugging are required.", user_id="alpha"
    ), alpha)
    beta_resume = generate_local_content(scoped_job(
        "Firmware Intern", "C, FreeRTOS, UART, PWM, and microcontrollers are required.", user_id="beta"
    ), beta)

    assert "Internship Radar - AI Resume Tailoring Platform" in project_names(alpha_resume)
    assert "Internship Radar - AI Resume Tailoring Platform" not in project_names(beta_resume)
    assert "Python" not in beta_resume.selected_skills
