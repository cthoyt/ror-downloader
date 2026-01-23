"""Download and process ROR."""

from __future__ import annotations

import datetime
import json
import logging
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Literal, TypeAlias, overload

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
    "Organization",
    "OrganizationType",
    "Relationship",
    "Status",
    "VersionInfo",
    "VersionInfoShort",
    "get_organizations",
    "get_version_info",
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

#: The type of an organization
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


#: The status of a record describing an organization
Status: TypeAlias = Literal["active", "inactive", "withdrawn"]


class Organization(BaseModel):
    """A ROR record describing an organization."""

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

    def get_description(self: Organization) -> str | None:
        """Generate a description."""
        description = (
            f"{DESCRIPTION_PREFIX[self.types[0]]} in {self.locations[0].geonames_details.name}"
        )
        if self.established:
            description += f" established in {self.established}"
        return description


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


class VersionInfoShort(BaseModel):
    """A version information tuple."""

    version: str
    url: str
    date: datetime.date | None = None


class VersionInfo(VersionInfoShort):
    """A version information tuple with the downloaded path."""

    path: Path


# docstr-coverage:excused `overload`
@overload
def get_version_info(
    *, force: bool = ..., authenticate_zenodo: bool = ..., download: Literal[True] = ...
) -> VersionInfo: ...


# docstr-coverage:excused `overload`
@overload
def get_version_info(
    *, force: bool = ..., authenticate_zenodo: bool = ..., download: Literal[False] = ...
) -> VersionInfoShort: ...


def get_version_info(
    *, force: bool = False, authenticate_zenodo: bool = True, download: bool = True
) -> VersionInfo | VersionInfoShort:
    """Ensure the latest ROR record, metadata, and filepath.

    :param force: Should the record be downloaded again? This almost
        never needs to be true, since the data doesn't change for
        a given version
    :param authenticate_zenodo: Should Zenodo be authenticated?
        This isn't required, but can help avoid rate limits
    :param download: Should the downloaded file be returned?
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
    date = response_json["metadata"].get("publication_date")
    if download:
        path = client.download(latest_record_id, name=name, force=force)
        return VersionInfo(version=version, url=url, path=path, date=date)
    else:
        return VersionInfoShort(version=version, url=url, date=date)


@lru_cache
def get_organizations(
    *, force: bool = False, authenticate_zenodo: bool = True, progress: bool = True
) -> tuple[VersionInfo, list[Organization]]:
    """Get the latest ROR metadata and records."""
    status = get_version_info(force=force, authenticate_zenodo=authenticate_zenodo, download=True)
    with zipfile.ZipFile(status.path) as zf:
        for zip_info in zf.filelist:
            if zip_info.filename.endswith(".json"):
                with zf.open(zip_info) as file:
                    organizations = [
                        Organization.model_validate(organization)
                        for organization in tqdm(
                            json.load(file), unit_scale=True, disable=not progress
                        )
                    ]
                    return status, organizations
    raise FileNotFoundError
