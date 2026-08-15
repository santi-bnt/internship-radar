from app.sources.greenhouse import GreenhouseAdapter


def test_greenhouse_filters_for_student_roles():
    accepted = [
        "Software Engineering Intern",
        "Firmware Internship - Summer 2027",
        "Electrical Engineering Co-op",
        "Student Robotics Program",
    ]
    rejected = [
        "Senior Software Engineer",
        "Staff FPGA Engineer",
        "Engineering Manager",
        "University Recruiter",
    ]

    assert all(GreenhouseAdapter.is_internship_title(title) for title in accepted)
    assert not any(
        GreenhouseAdapter.is_internship_title(title) for title in rejected
    )
