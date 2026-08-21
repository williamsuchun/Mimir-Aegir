"""Optional Azure boundaries; never imported by the local pipeline."""

from __future__ import annotations

import os
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator

from .models import EvidenceSet, StrictModel


class AzureConfigurationError(ValueError):
    pass


class FoundrySettings(StrictModel):
    endpoint: str
    deployment: str
    region: str
    api_surface: Literal["openai-v1-responses"] = "openai-v1-responses"

    @model_validator(mode="after")
    def validate_endpoint(self) -> "FoundrySettings":
        parsed = urlparse(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("endpoint must be an HTTPS resource endpoint without query or fragment")
        if not self.deployment.strip() or not self.region.strip():
            raise ValueError("deployment and region must be explicit non-empty values")
        return self

    @property
    def responses_base_url(self) -> str:
        return f"{self.endpoint.rstrip('/')}/openai/v1/"

    @classmethod
    def from_environment(cls) -> "FoundrySettings":
        names = (
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_REGION",
        )
        values = {name: os.environ.get(name, "").strip() for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise AzureConfigurationError(
                f"missing required Azure setting(s): {', '.join(missing)}"
            )
        return cls(
            endpoint=values["AZURE_OPENAI_ENDPOINT"],
            deployment=values["AZURE_OPENAI_DEPLOYMENT"],
            region=values["AZURE_OPENAI_REGION"],
        )


class CloudEvidenceItem(StrictModel):
    candidate_id: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    provenance_claim_ids: list[str]
    model_generated: Literal[True] = True
    human_review_required: Literal[True] = True


class CloudEvidenceEnvelope(StrictModel):
    schema_version: Literal["mimir.aegir.cloud-evidence.v1"]
    items: list[CloudEvidenceItem]


class BlobCreatedEvent(StrictModel):
    eventType: Literal["Microsoft.Storage.BlobCreated"]
    subject: str
    data: dict[str, Any]

    @model_validator(mode="after")
    def validate_blob_event(self) -> "BlobCreatedEvent":
        prefix = "/blobServices/default/containers/"
        marker = "/blobs/"
        if not self.subject.startswith(prefix) or marker not in self.subject[len(prefix) :]:
            raise ValueError("event subject is not a container/blob path")
        blob_url = self.data.get("url")
        content_type = self.data.get("contentType")
        if not isinstance(blob_url, str) or urlparse(blob_url).scheme != "https":
            raise ValueError("BlobCreated data.url must be HTTPS")
        if not isinstance(content_type, str) or not content_type:
            raise ValueError("BlobCreated data.contentType must be present")
        return self


def create_responses_client(
    settings: FoundrySettings, credential: Any | None = None
) -> Any:
    """Create the official OpenAI client with an Entra token provider."""
    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import OpenAI
    except ImportError as error:
        raise AzureConfigurationError(
            "install the optional Azure dependencies with: python -m pip install '.[azure]'"
        ) from error
    token_provider = get_bearer_token_provider(
        credential or DefaultAzureCredential(),
        "https://ai.azure.com/.default",
    )
    return OpenAI(base_url=settings.responses_base_url, api_key=token_provider)


def request_cloud_evidence(
    client: Any,
    settings: FoundrySettings,
    evidence: EvidenceSet,
    *,
    instructions: str,
) -> CloudEvidenceEnvelope:
    """Request strict semantic enrichment and revalidate all provenance links."""
    if not instructions.strip():
        raise AzureConfigurationError("instructions must be explicit and non-empty")
    response = client.responses.parse(
        model=settings.deployment,
        instructions=instructions,
        input=evidence.model_dump_json(),
        text_format=CloudEvidenceEnvelope,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise AzureConfigurationError("Foundry response did not contain parsed evidence")
    envelope = CloudEvidenceEnvelope.model_validate(parsed)
    candidate_ids = {claim.candidate_id for claim in evidence.claims}
    claim_ids = {claim.claim_id for claim in evidence.claims}
    for item in envelope.items:
        if item.candidate_id not in candidate_ids:
            raise AzureConfigurationError(
                f"cloud evidence references unknown candidate: {item.candidate_id}"
            )
        unknown_claims = set(item.provenance_claim_ids) - claim_ids
        if unknown_claims:
            raise AzureConfigurationError(
                "cloud evidence references unknown claim(s): "
                + ", ".join(sorted(unknown_claims))
            )
        if not item.provenance_claim_ids:
            raise AzureConfigurationError("cloud evidence must cite at least one local claim")
    return envelope
