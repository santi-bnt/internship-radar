from app.services.normalization import clean_job_content, clean_text


def test_escaped_html_is_decoded_before_plain_text_cleanup():
    content = "&lt;h3&gt;About Zipline&lt;/h3&gt;&lt;p&gt;Fast &amp;amp; reliable.&lt;/p&gt;"

    assert clean_text(content) == "About Zipline Fast & reliable."


def test_job_content_preserves_safe_structure_and_entities():
    content = (
        '&lt;h3&gt;About Zipline&lt;/h3&gt;'
        '&lt;p&gt;Fast &amp;amp; reliable.&amp;nbsp;&lt;/p&gt;'
        '&lt;ul&gt;&lt;li&gt;&lt;strong&gt;Validate&lt;/strong&gt; systems.&lt;/li&gt;&lt;/ul&gt;'
    )

    normalized = clean_job_content(content)

    assert "<h3>About Zipline</h3>" in normalized
    assert "<p>Fast &amp; reliable." in normalized
    assert "<ul><li><strong>Validate</strong> systems.</li></ul>" in normalized
    assert "&lt;h3&gt;" not in normalized


def test_job_content_removes_unsafe_tags_and_link_protocols():
    content = (
        '<script>alert("x")</script>'
        '<p><a href="javascript:alert(1)">Unsafe</a> '
        '<a href="https://example.com/job">Official job</a></p>'
    )

    normalized = clean_job_content(content)

    assert "<script" not in normalized
    assert "javascript:" not in normalized
    assert 'href="https://example.com/job"' in normalized
