import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request


class ApicurioSchemaRegistryClient:
    """Client for fetching AVRO schemas from Apicurio Schema Registry."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (
            str(base_url).strip()
            if isinstance(base_url, str) and base_url.strip()
            else str(os.getenv("APICURIO_REGISTRY_URL", "")).strip()
        )

    def fetch_avro_schema(self, subject: str, version: str, group_id: str = "default") -> dict:
        if not self.base_url:
            raise ValueError("APICURIO_REGISTRY_URL env var (or schema.registry.url) is required")

        endpoint = (
            f"{self.base_url.rstrip('/')}/apis/registry/v2/groups/"
            f"{urllib.parse.quote(group_id, safe='')}/artifacts/{urllib.parse.quote(subject, safe='')}/"
            f"versions/{urllib.parse.quote(version, safe='')}/content"
        )
        request = urllib.request.Request(endpoint, method="GET")
        request.add_header("Accept", "application/json")
        self._add_auth_headers(request)

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise ValueError(
                f"Apicurio schema fetch failed for subject='{subject}', version='{version}' with status {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Apicurio schema fetch failed: {exc.reason}") from exc

        try:
            schema_obj = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("Apicurio returned non-JSON schema content for AVRO artifact") from exc

        if not isinstance(schema_obj, dict):
            raise ValueError("Apicurio returned invalid AVRO schema payload")
        return schema_obj

    def _add_auth_headers(self, request: urllib.request.Request):
        token = str(os.getenv("APICURIO_REGISTRY_TOKEN", "")).strip()
        username = str(os.getenv("APICURIO_REGISTRY_USERNAME", "")).strip()
        password = str(os.getenv("APICURIO_REGISTRY_PASSWORD", "")).strip()

        if token:
            request.add_header("Authorization", f"Bearer {token}")
            return

        if username:
            basic = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            request.add_header("Authorization", f"Basic {basic}")


def fetch_apicurio_schema(subject: str, version: str, group_id: str = "default", base_url: str | None = None) -> dict:
    client = ApicurioSchemaRegistryClient(base_url=base_url)
    return client.fetch_avro_schema(subject=subject, version=version, group_id=group_id)
