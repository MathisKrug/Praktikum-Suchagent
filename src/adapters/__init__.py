"""Adapter-Registry."""

from .base import Adapter, AdapterError
from .json_apis import (
    WorkdayAdapter,
    SmartRecruitersAdapter,
    GreenhouseAdapter,
    LeverAdapter,
    ZalandoAdapter,
)
from .html_sites import (
    SuccessFactorsAdapter,
    TeamtailorAdapter,
    EployAdapter,
    GenericHtmlAdapter,
)

REGISTRY = {
    "workday": WorkdayAdapter,
    "smartrecruiters": SmartRecruitersAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "zalando": ZalandoAdapter,
    "successfactors": SuccessFactorsAdapter,
    "teamtailor": TeamtailorAdapter,
    "eploy": EployAdapter,
    "generic_html": GenericHtmlAdapter,
}


def build(company: dict, search_terms: list[str]) -> Adapter:
    name = company.get("adapter")
    cls = REGISTRY.get(name)
    if not cls:
        raise AdapterError(
            f"Unbekannter Adapter '{name}' fuer {company.get('name')}. "
            f"Moeglich sind: {', '.join(sorted(REGISTRY))}"
        )
    return cls(company, search_terms)


__all__ = ["build", "REGISTRY", "Adapter", "AdapterError"]
