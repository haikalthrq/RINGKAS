from datetime import date
from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StrictInt, field_validator


class PublicationMetadata(BaseModel):
    """Internal metadata only; not a claim about the official BPS response schema."""

    model_config = ConfigDict(extra="ignore")

    external_id: str | None = None
    title: Annotated[str, Field(min_length=1)]
    publication_year: StrictInt = Field(gt=0)
    release_date: date | None = None
    region: Annotated[str, Field(min_length=1)]
    region_level: Annotated[str, Field(min_length=1)]
    topic: str | None = None
    catalog_number: str | None = None
    publication_number: str | None = None
    source_page_url: AnyHttpUrl
    pdf_url: AnyHttpUrl | None = None
    language: str | None = None

    @field_validator("source_page_url")
    @classmethod
    def source_url_must_not_contain_credentials_or_query(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username is not None or value.password is not None or value.query or value.fragment:
            raise ValueError("source URL must not contain credentials, query, or fragment")
        return value

    @field_validator("pdf_url")
    @classmethod
    def pdf_url_must_not_contain_credentials_or_fragment(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and (value.username is not None or value.password is not None or value.fragment):
            raise ValueError("PDF URL must not contain credentials or fragment")
        return value

    @field_validator("title", "region", "region_level")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required metadata text must not be blank")
        return value
