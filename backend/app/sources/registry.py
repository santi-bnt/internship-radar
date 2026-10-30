from app.sources.amazon_jobs import AmazonJobsAdapter
from app.sources.base import JobSourceAdapter
from app.sources.embedded_jobs import EmbeddedJobsAdapter
from app.sources.greenhouse import GreenhouseAdapter
from app.sources.lever import LeverAdapter
from app.sources.local_json import LocalJsonAdapter
from app.sources.official_careers import OfficialCareersAdapter
from app.sources.oracle_recruiting import OracleRecruitingAdapter
from app.sources.smartrecruiters import SmartRecruitersAdapter
from app.sources.workday import WorkdayAdapter
from app.sources.community import CommunityRepositoryAdapter


ADAPTERS: dict[str, type[JobSourceAdapter]] = {
    "local_json": LocalJsonAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "embedded_jobs": EmbeddedJobsAdapter,
    "amazon_jobs": AmazonJobsAdapter,
    "official_careers": OfficialCareersAdapter,
    "oracle_recruiting": OracleRecruitingAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "workday": WorkdayAdapter,
    "community_repo": CommunityRepositoryAdapter,
}


def create_adapter(source, search_criteria: dict | None = None) -> JobSourceAdapter:
    adapter_class = ADAPTERS.get(source.source_type)
    if not adapter_class:
        raise ValueError(f"No fetch adapter is available for source type '{source.source_type}'")
    return adapter_class(
        source.company,
        source.source_identifier,
        source.source_url,
        search_criteria=search_criteria,
    )
