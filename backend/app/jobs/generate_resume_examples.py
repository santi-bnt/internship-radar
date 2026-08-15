from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfReader
from sqlalchemy import select

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models import ResumeProfile
from app.services.resume_generation import generate_resume
from app.services.seed import seed_profile_and_sources


EXAMPLE_JOBS = (
    (
        "intel-software-engineer-intern",
        "Intel Software Engineer Intern",
        "Develop and validate production software in C++ and Python on Linux. "
        "Build multithreaded components, debug failures, and improve software validation.",
        "Required: C++, Python, Linux, multithreaded programming, debugging, "
        "data structures, and software development.",
        "Preferred: software validation, algorithms, Git, x86 Assembly, and Intel Xeon.",
    ),
    (
        "embedded-firmware-intern",
        "Embedded Firmware Intern",
        "Develop embedded firmware for microcontroller products and integrate hardware interfaces.",
        "Required: C, C++, FreeRTOS, embedded systems, microcontrollers, UART, "
        "GPIO, interrupts, and hardware debugging.",
        "Preferred: Linux, PWM, ADC, software debugging, and validation.",
    ),
    (
        "backend-software-intern",
        "Backend Software Engineering Intern",
        "Build reliable Python services and REST APIs backed by relational databases.",
        "Required: Python, FastAPI, PostgreSQL, SQL, REST APIs, Git, and Linux.",
        "Preferred: Docker, SQLAlchemy, object-oriented programming, and testing.",
    ),
)


def _job(title: str, description: str, requirements: str, preferred: str) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        company="Resume Skills Validation",
        location="North America",
        country="United States",
        description=description,
        requirements=requirements,
        preferred_qualifications=preferred,
        analysis=None,
    )


def main() -> None:
    output_dir = Path(
        os.environ.get(
            "RESUME_EXAMPLE_OUTPUT_DIR",
            str(Path(__file__).resolve().parents[3] / "output" / "pdf"),
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    summaries: list[dict[str, object]] = []
    with SessionLocal() as db:
        seed_profile_and_sources(db)
        profile = db.scalar(select(ResumeProfile).limit(1))
        if profile is None:
            raise RuntimeError("The verified resume profile could not be loaded.")
        for index, (slug, title, description, requirements, preferred) in enumerate(
            EXAMPLE_JOBS,
            start=1,
        ):
            content, latex_source, pdf_bytes = generate_resume(
                _job(title, description, requirements, preferred),
                profile,
                generation_id=-index,
            )
            page_count = len(PdfReader(BytesIO(pdf_bytes)).pages)
            if page_count != 1:
                raise RuntimeError(f"{title} produced {page_count} PDF pages.")
            (output_dir / f"{slug}.pdf").write_bytes(pdf_bytes)
            (output_dir / f"{slug}.tex").write_text(latex_source, encoding="utf-8")
            summary = {
                "title": title,
                "classification": content.classification,
                "page_count": page_count,
                "selected_skills": content.selected_skills,
                "skill_categories": [
                    group.model_dump() for group in content.skill_categories
                ],
                "job_skill_matches": [
                    item.model_dump() for item in content.job_skill_matches
                ],
                "verification": content.skill_verification.model_dump(),
            }
            (output_dir / f"{slug}.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            summaries.append(summary)
    (output_dir / "resume-skill-examples.json").write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summaries, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
