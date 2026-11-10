"""Generic role views and implemented-only evidence; no candidate dataset."""
from copy import deepcopy
import re

def project_role_view(source, family):
    """Detached role view of the same verified project, not a second project."""
    view = deepcopy(source)
    if family in source.get("role_bullets", {}):
        view["bullets"] = list(source["role_bullets"][family])
    if family in source.get("role_technologies", {}):
        view["technologies"] = list(source["role_technologies"][family])
    return view


def implemented_claims(values):
    """Keep implemented clauses, excluding roadmap/pending qualifications.

    A design bullet may correctly end with a pending fabrication disclaimer;
    that disclaimer must not earn electrical-validation or firmware credit.
    """
    for value in values:
        text = str(value)
        if re.match(r"\s*(planned|pending|todo|in progress)\b", text, re.I):
            continue
        text = re.sub(r"\bwith\b[^.;]*\bpending\b", "", text, flags=re.I)
        for clause in re.split(r"[;.]", text):
            if not re.search(r"\b(planned|pending|todo|in progress)\b", clause, re.I):
                yield clause
