# Public release boundary

This snapshot updates the independent public showcase with generic application features. It does not merge private git history. Production secrets, environment files, databases, attachments, generated CVs, personal profile/project/certification datasets and automatic per-person import/override lists are excluded or replaced with synthetic examples.

The published demo accepts reads only. Its backend/database and signing secrets must be dedicated to the demo, never production. Forks start locked with email and scheduled automation disabled. The local vision model binds to numeric loopback and rejects cloud models; the browser portal cannot reach local services.

Tests tied exclusively to private profile provisioning are omitted. Generic security, classification, deduplication, evidence, navigation, ingestion and assistant tests are included. Configure your own verified candidate profile before generating a real CV.

For distinct authenticated candidate identities, configure `CANDIDATE_ACCOUNT_IDS` with the same JSON email-to-user-ID mapping on frontend and backend. No real account allowlist is embedded in source. Configure these values in your deployment environment, never commit them.
