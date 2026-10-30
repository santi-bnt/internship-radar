from app.services.dedupe import find_duplicate, same_job


def test_same_external_id_and_source_deduplicates():
    left = {
        "external_id": "123",
        "source_name": "Greenhouse",
        "company": "NXP",
        "title": "Firmware Intern",
        "location": "Austin",
    }
    right = {**left, "title": "Firmware Intern - Summer"}
    assert same_job(left, right)
    assert find_duplicate([left], right) is left


def test_similar_title_does_not_merge_different_locations():
    left = {
        "external_id": None,
        "source_name": "Official",
        "company": "Intel",
        "title": "FPGA Intern",
        "location": "Mexico",
        "description": "RTL design and verification for networking products.",
    }
    right = {
        **left,
        "location": "Canada",
        "description": "RTL design and verification for networking products.",
    }
    assert not same_job(left, right)


def test_apply_url_is_a_strong_deduplication_key():
    left = {
        "company": "AMD",
        "title": "ASIC Intern",
        "location": "Austin",
        "apply_url": "https://jobs.example.com/42/",
    }
    right = {
        "company": "AMD Inc.",
        "title": "Graduate ASIC Intern",
        "location": "Remote",
        "apply_url": "https://jobs.example.com/42",
    }
    assert same_job(left, right)


def test_tracking_query_parameters_do_not_create_another_canonical_job():
    left = {
        "company": "Plexus",
        "title": "Intern, Software Development",
        "location": "Zapopan, Jalisco, Mexico",
        "apply_url": "https://careers.example.com/jobs/99?jobId=99&utm_source=linkedin&ref=feed",
    }
    right = {
        **left,
        "apply_url": "https://careers.example.com/jobs/99?trackingId=abc&jobId=99&utm_medium=social",
    }
    assert same_job(left, right)
