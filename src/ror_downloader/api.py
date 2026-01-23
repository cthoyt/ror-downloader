"""Download and process ROR."""

from __future__ import annotations

import datetime
import json
import logging
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Literal, NamedTuple, TypeAlias

import zenodo_client
from pydantic import BaseModel
from tqdm.auto import tqdm

__all__ = [
    "Admin",
    "DateAnnotated",
    "ExternalID",
    "Link",
    "Location",
    "LocationDetails",
    "Name",
    "OrganizationType",
    "RORStatus",
    "Record",
    "Relationship",
    "Status",
    "get_description",
    "get_ror_records",
    "get_ror_status",
]

logger = logging.getLogger(__name__)
ROR_ZENODO_RECORD_ID = "17953395"

NAME_REMAPPING = {
    "'s-Hertogenbosch": "Den Bosch",  # SMH Netherlands, why u gotta be like this
    "'s Heeren Loo": "s Heeren Loo",
    "'s-Heerenberg": "s-Heerenberg",
    "Institut Virion\\Serion": "Institut Virion/Serion",
    "Hematology\\Oncology Clinic": "Hematology/Oncology Clinic",
}

OrganizationType: TypeAlias = Literal[
    "education",
    "facility",
    "funder",
    "company",
    "government",
    "healthcare",
    "archive",
    "nonprofit",
    "other",
]

_MISSED_ORG_TYPES: set[str] = set()


class LocationDetails(BaseModel):
    """The location details slot in the ROR schema."""

    continent_code: str
    continent_name: str
    country_code: str
    country_name: str
    country_subdivision_code: str | None = None
    country_subdivision_name: str | None = None
    lat: float
    lng: float
    name: str


class Location(BaseModel):
    """The location slot in the ROR schema."""

    geonames_id: int
    geonames_details: LocationDetails


class ExternalID(BaseModel):
    """The external ID slot in the ROR schema."""

    type: str
    all: list[str]
    preferred: str | None = None


class Link(BaseModel):
    """The link slot in the ROR schema."""

    type: str
    value: str


class Name(BaseModel):
    """The name slot in the ROR schema."""

    value: str
    types: list[str]
    lang: str | None = None


class Relationship(BaseModel):
    """The relationship slot in the ROR schema."""

    type: str
    label: str
    id: str


class DateAnnotated(BaseModel):
    """The annotated date slot in the ROR schema."""

    date: datetime.date
    schema_version: str


class Admin(BaseModel):
    """The admin slot in the ROR schema."""

    created: DateAnnotated
    last_modified: DateAnnotated


Status: TypeAlias = Literal["active", "inactive", "withdrawn"]


class Record(BaseModel):
    """A ROR record."""

    locations: list[Location]
    established: int | None = None
    external_ids: list[ExternalID]
    id: str
    domains: list[str]
    links: list[Link]
    names: list[Name]
    relationships: list[Relationship]
    status: Status
    types: list[OrganizationType]
    admin: Admin

    def get_preferred_label(self) -> str | None:
        """Get the preferred label."""
        primary_name: str | None = None
        for name in self.names:
            if "ror_display" in name.types:
                primary_name = name.value
        if primary_name is None:
            return None
        primary_name = NAME_REMAPPING.get(primary_name, primary_name)
        return primary_name


DESCRIPTION_PREFIX = {
    "education": "an educational organization",
    "facility": "a facility",
    "funder": "a funder",
    "company": "a company",
    "government": "a governmental organization",
    "healthcare": "a healthcare organization",
    "archive": "an archive",
    "nonprofit": "a nonprofit organization",
    "other": "an organization",
}


def get_description(record: Record) -> str | None:
    """Generate a description."""
    description = (
        f"{DESCRIPTION_PREFIX[record.types[0]]} in {record.locations[0].geonames_details.name}"
    )
    if record.established:
        description += f" established in {record.established}"
    return description


class RORStatus(NamedTuple):
    """A version information tuple."""

    version: str
    url: str
    path: Path


def get_ror_status(*, force: bool = False, authenticate_zenodo: bool = True) -> RORStatus:
    """Ensure the latest ROR record, metadata, and filepath.

    :param force: Should the record be downloaded again? This almost
        never needs to be true, since the data doesn't change for
        a given version
    :param authenticate_zenodo: Should Zenodo be authenticated?
        This isn't required, but can help avoid rate limits
    :return: A version information tuple

    .. note::

        this goes into the ``~/.data/zenodo/6347574`` folder,
        because 6347574 is the super-record ID, which groups all
        versions together. this is different from the value
        for :data:`ROR_ZENODO_RECORD_ID`
    """
    client = zenodo_client.Zenodo()
    latest_record_id = client.get_latest_record(
        ROR_ZENODO_RECORD_ID, authenticate=authenticate_zenodo
    )
    response = client.get_record(latest_record_id, authenticate=authenticate_zenodo)
    response_json = response.json()
    version = response_json["metadata"]["version"].lstrip("v")
    file_record = response_json["files"][0]
    name = file_record["key"]
    url = file_record["links"]["self"]
    path = client.download(latest_record_id, name=name, force=force)
    return RORStatus(version=version, url=url, path=path)


@lru_cache
def get_ror_records(
    *, force: bool = False, authenticate_zenodo: bool = True
) -> tuple[RORStatus, list[Record]]:
    """Get the latest ROR metadata and records."""
    status = get_ror_status(force=force, authenticate_zenodo=authenticate_zenodo)
    with zipfile.ZipFile(status.path) as zf:
        for zip_info in zf.filelist:
            if zip_info.filename.endswith(".json"):
                with zf.open(zip_info) as file:
                    records = [
                        Record.model_validate(record)
                        for record in tqdm(json.load(file), unit_scale=True)
                    ]
                    return status, records
    raise FileNotFoundError
