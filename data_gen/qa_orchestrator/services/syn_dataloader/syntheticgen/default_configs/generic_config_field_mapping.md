# Generic Config Field Reference

## Top-level keys

| Key | Required | Default | Allowed values |
|---|---|---|---|
| general | Yes | N/A | Object |
| output | Yes | N/A | Object |
| rules | Yes | N/A | Object |
| schema | Yes | N/A | Object |

## general

| Key | Required | Default | Allowed values |
|---|---|---|---|
| general.seed | No | None | Integer |
| general.start_time | No | None | ISO datetime string or datetime |
| general.end_time | No | None | ISO datetime string or datetime |
| general.duration_hours | No | 1 | Integer-like |
| general.default_frequency | No | 1min | <number><unit>, units: second, seconds, sec, s, min, mins, minute, minutes, m, hour, hours, h, hr, hrs |

## output

| Key | Required | Default | Allowed values |
|---|---|---|---|
| output.sink | No | None | db or any string |
| output.type | Conditional | None | postgresql, postgres, pg, mssql, sqlserver, sql_server, azure_sql, azuresql |

Conditional rule:
- output.type is required when output.sink is db.

## rules

| Key | Required | Default | Allowed values |
|---|---|---|---|
| rules.entity_file | No | None | Path string |
| rules.calculated_field | No | None | Object: field -> formula |

## schema

| Key | Required | Default | Allowed values |
|---|---|---|---|
| schema.source | No | yaml | yaml, local_avsc, local_avro, apicurio_registry |
| schema.table_defaults | No | {} | Object |
| schema.field_mapping | No | {} | Object |
| schema.record_rate_field | No | record_count (table mode) | String |
| schema.range_field_mapping | No | {} | Object |
| schema.avro | Conditional | {} | Object |
| schema.registry | Conditional | {} | Object |

### schema.table_defaults

Use `schema.table_defaults` to define table-level options that should apply across all tables,
including tables generated from AVRO schemas.

| Key | Required | Default | Allowed values |
|---|---|---|---|
| schema.table_defaults.record_count | No | rules.defaults.record_count or 60 | Integer-like |
| schema.table_defaults.allow_duplicate_timestamps | No | false | true, false |
| schema.table_defaults.load_mode | No | None | append, truncate_load, truncate, truncate_and_load, drop_recreate, drop_and_recreate, replace |

Precedence for table options:
- `schema.tables.<table>.<option>` (highest)
- `schema.table_defaults.<option>`
- legacy `schema.<option>` (backward compatibility)
- built-in fallback (lowest)

Source-specific rules:
- `schema.source = yaml`
	- Use existing `schema.tables` format, or `schema.columns` (list of column names) for shorthand.
- `schema.source = local_avsc` or `schema.source = local_avro`
	- Requires `schema.avro.path`
	- Optional `schema.avro.table_name`
- `schema.source = apicurio_registry`
	- Requires `schema.registry.subject` and `schema.registry.version`
	- Optional `schema.registry.group_id` (default: `default`)
	- Optional `schema.registry.url` (falls back to `APICURIO_REGISTRY_URL`)
	- Optional `schema.registry.table_name`

### schema.avro

Used only when `schema.source` is `local_avsc` or `local_avro`.

| Key | Required | Default | Allowed values |
|---|---|---|---|
| schema.avro.path | Yes | None | Absolute or relative file path |
| schema.avro.table_name | No | Derived from output/db_config/x-sql-table/avro name | String |

### schema.registry

Used only when `schema.source` is `apicurio_registry`.

| Key | Required | Default | Allowed values |
|---|---|---|---|
| schema.registry.url | No | APICURIO_REGISTRY_URL env var | HTTP(S) URL |
| schema.registry.group_id | No | default | String |
| schema.registry.subject | Yes | None | String |
| schema.registry.version | Yes | None | Integer-like or string version |
| schema.registry.table_name | No | Derived from output/db_config/x-sql-table/avro name | String |

## schema.tables.table_name (your table_name)

| Key | Required | Default | Allowed values |
|---|---|---|---|
| schema.tables.table_name.columns | Yes (type-based mode) | None | Object: column_name -> column config |
| schema.tables.table_name.record_count | No | None | Integer-like |
| schema.tables.table_name.allow_duplicate_timestamps | No | false | true, false |
| schema.tables.table_name.load_mode | No | truncate_load | append, truncate_load, truncate, truncate_and_load, drop_recreate, drop_and_recreate, replace |

## schema.tables.table_name.columns.column_name (your column_name)

| Key | Required | Default | Allowed values |
|---|---|---|---|
| type | No | string | See type list below |
| nullable | No | true | true, false |
| primary_key | No | false | true, false |
| server_default | No | None | SQL expression string |
| length | No | None | Integer-like |
| precision | No | None | Integer-like |
| scale | No | None | Integer-like |
| min | No | 0 | Number |
| max | No | 100 | Number |
| semantic | No | None | first_name, last_name, full_name, name, email, email_address, username, user_name, login, company, organization, organisation, country, country_name, country_code, iso_country_code |
| values | No | None | Array |
| values_probabilities | No | None | Numeric array (same length as values) |
| null_probability | No | None | Number in [0, 1] |
| true_probability | No | None | Number in [0, 1] |
| enum_name | No | Generated for AVRO enum fields | Valid PostgreSQL type identifier string |
| enum_schema | No | None | PostgreSQL schema name string |
| create_type | No | true | true, false |

Additional notes for `categorical/category/enum` columns:
- `values` should be provided when using DB enum type generation.
- `enum_name` is required by PostgreSQL enum creation; AVRO enum mapping auto-generates this when missing.
- `create_type` controls whether enum type DDL is emitted.

## AVRO custom x-* annotation mapping

When using AVRO sources, these custom attributes are supported and mapped to internal config fields.

### Record-level x-* keys

| AVRO key | Mapped config key | Allowed values |
|---|---|---|
| x-record-count | schema.tables.<table>.record_count | Integer-like |
| x-sql-table | schema.tables table name fallback | String |
| x-primary-key | schema.tables.<table>.columns.<col>.primary_key | Array of field names |
| x-load-mode | schema.tables.<table>.load_mode | append, truncate_load, truncate, truncate_and_load, drop_recreate, drop_and_recreate, replace |
| x-allow-duplicate-timestamps | schema.tables.<table>.allow_duplicate_timestamps | true, false |
| x-sql-schema | schema.tables.<table>.target_schema metadata | String |

### Field-level x-* keys

| AVRO key | Mapped column key | Allowed values |
|---|---|---|
| x-min | min | Number, ISO date string, ISO datetime string |
| x-max | max | Number, ISO date string, ISO datetime string |
| x-null-probability | null_probability | Number in [0, 1] |
| x-true-probability | true_probability | Number in [0, 1] |
| x-values-probabilities | values_probabilities | Numeric array (same length as values) |
| x-server-default | server_default | SQL expression string |
| x-semantic | semantic | See semantic values above |

## Supported type values for type

- string, varchar, text, citext, char, unicode, nvarchar, nchar, xml, clob
- uuid, uniqueidentifier
- json, jsonb
- binary, varbinary, blob, bytea
- integer, int, int4, serial
- bigint, int8, bigserial
- smallint, int2, tinyint
- numeric, decimal, dec
- float, double, number, numericfloat, real, doubleprecision
- datetime, timestamp, datetime2, smalldatetime
- datetimeoffset, timestamptz
- date, time
- boolean, bool, bit
- categorical, category, enum
