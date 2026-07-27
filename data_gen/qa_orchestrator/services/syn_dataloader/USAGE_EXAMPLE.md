# run_synthetic Quick Usage

Use `run_synthetic()` to generate synthetic records from a config.

Choose one of these modes:
- With `entity_file`: use predefined entities/tags and ranges.
- Without `entity_file`: generate values from column types in schema.
- No input config: use default packaged config.
- AVRO schema-driven: use `schema.source` as `local_avsc`, `local_avro`, or `apicurio_registry`.

## 1) With entity file

Use this when you already have an entity YAML (for example, known tags/assets).

```python
import asyncio
from datetime import datetime, timedelta, timezone
from qa_orchestrator.services.syn_dataloader.load_data import run_synthetic


async def main():
    config_file = "/absolute/path/to/your_config.yaml"
    entity_file = "/absolute/path/to/your_entity.yaml"

    now = datetime.now(timezone.utc)

    data_config = {
        "historian": {
            "config_file": config_file,
            "overrides": {
                "general": {
                    "start_time": now - timedelta(hours=2),
                    "end_time": now,
                },
                "rules": {
                    "entity_file": entity_file,
                },
            },
        }
    }

    await run_synthetic(data_sources_config=data_config)


asyncio.run(main())
```

## 2) Without entity file (type-based generation)

Use this when your table schema is defined and you want automatic value generation by data type.

```python
import asyncio
from qa_orchestrator.services.syn_dataloader.load_data import run_synthetic


async def main():
    config_file = "/absolute/path/to/your_config.yaml"

    data_config = {
        "azure_sql": {
            "config_file": config_file,
            # no rules.entity_file -> type-based generation
        }
    }

    await run_synthetic(data_sources_config=data_config)


asyncio.run(main())
```

## 3) Default run

Use this for a quick smoke test with default config.

```python
import asyncio
from qa_orchestrator.services.syn_dataloader.load_data import run_synthetic


async def main():
    await run_synthetic()


asyncio.run(main())
```

## 4) AVRO schema-driven generation (local AVSC)

Use this when your schema is in a local `.avsc` file and you want generation + table creation from AVRO fields.

```yaml
# config.yaml
general:
  duration_hours: 1
  default_frequency: "1sec"

output:
  sink: db
  type: postgresql

schema:
  source: local_avsc
  table_defaults:
    load_mode: drop_recreate
    allow_duplicate_timestamps: true
    record_count: 1000
  avro:
    path: /absolute/path/to/sample_user.avsc
    table_name: user_abc

rules:
  entity_file:
```

```python
import asyncio
from qa_orchestrator.services.syn_dataloader.load_data import run_synthetic


async def main():
    data_config = {
        "postgres": {
            "config_file": "/absolute/path/to/config.yaml",
        }
    }

    await run_synthetic(data_sources_config=data_config)


asyncio.run(main())
```

## 5) AVRO schema-driven generation (local AVRO binary)

Use this when your schema should be read from Avro OCF writer schema in a `.avro` file.

```yaml
schema:
  source: local_avro
  avro:
    path: /absolute/path/to/sample_data.avro
    table_name: user_abc
```

Notes:
- If `.avro` content is not a valid Avro OCF binary, loader falls back to JSON schema parsing.

## 6) AVRO schema-driven generation (Apicurio Schema Registry)

Use this when schema is stored in Apicurio and you want subject + explicit version resolution.

```yaml
schema:
  source: apicurio_registry
  registry:
    url: https://apicurio.example.com
    group_id: default
    subject: user-value
    version: "12"
    table_name: user_abc
```

Notes:
- Required keys: `registry.subject`, `registry.version`.
- `registry.group_id` defaults to `default`.
- `registry.url` is optional if `APICURIO_REGISTRY_URL` is set.

## 7) AVRO custom x-* annotations supported

These AVRO custom field attributes are mapped into generation behavior:
- `x-min`, `x-max` -> numeric/date bounds
- `x-null-probability` -> null generation probability
- `x-true-probability` -> boolean true probability
- `x-values-probabilities` -> weighted enum/value selection
- `x-semantic` -> faker-based semantic string generation (for example `first_name`, `email`)
- `x-server-default` -> DB server default expression

Table-level AVRO custom attributes currently supported:
- `x-record-count` -> table `record_count`
- `x-sql-table` -> default table name fallback
- `x-primary-key` -> marks listed columns as `primary_key`