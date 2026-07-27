import random
import string
import uuid
from datetime import datetime, timedelta
from typing import Any

try:
    from faker import Faker
except ModuleNotFoundError:
    Faker = None


class TypeBasedEntityGenerator:
    """
    Generates random values directly from column types.
    """

    COLUMN_TYPE_PATTERNS = {
        "datetime": ["timestamp", "date", "time", "created", "modified"],
        "boolean": ["is_", "has_", "flag", "enabled", "active", "deleted"],
        "numeric": ["count", "number", "value", "amount", "quantity", "agg_", "total", "sum"],
    }

    def __init__(self):
        self.faker = Faker() if Faker else None

    def detect_column_type(
        self,
        field_name: str,
        range_field_mapping: dict | None = None,
        output_column_types: dict | None = None,
        explicit_type: str | None = None,
    ) -> str:
        if explicit_type:
            return str(explicit_type).lower()

        if output_column_types and field_name in output_column_types:
            return str(output_column_types[field_name]).lower()

        field_lower = field_name.lower()
        if range_field_mapping and field_name in range_field_mapping:
            return "numeric"

        for column_type, patterns in self.COLUMN_TYPE_PATTERNS.items():
            if any(pattern in field_lower for pattern in patterns):
                return column_type

        return "string"

    def generate_value(
        self,
        field_name: str,
        column_type: str,
        config: dict[str, Any],
        timestamp: datetime | None = None,
        column_config: dict[str, Any] | None = None,
        use_rule_defaults: bool = True,
    ) -> Any:
        column_type = column_type.lower().strip()
        compact_type = column_type.replace("_", "").replace(" ", "")
        defaults = config.get("rules", {}).get("defaults", {}) if use_rule_defaults else {}
        column_config = column_config or {}

        if self._should_return_null(column_config):
            return None

        configured_values = column_config.get("values")
        if isinstance(configured_values, list) and configured_values:
            probabilities = column_config.get("values_probabilities")
            return self._pick_weighted_value(configured_values, probabilities)

        default_value = self._get_default_value(field_name, defaults)
        if default_value is not None:
            if isinstance(default_value, list):
                return random.choice(default_value)
            return default_value

        if compact_type in {
            "string",
            "text",
            "varchar",
            "char",
            "unicode",
            "nvarchar",
            "nchar",
            "citext",
            "xml",
            "clob",
        }:
            semantic_value = self._generate_semantic_string(column_config.get("semantic"))
            if semantic_value is not None:
                return semantic_value

            string_values = defaults.get("string_values")
            if isinstance(string_values, list) and string_values:
                return random.choice(string_values)

        if compact_type in {
            "datetime",
            "date",
            "timestamp",
            "datetime2",
            "smalldatetime",
            "datetimeoffset",
            "timestamptz",
        }:
            return self.generate_datetime_value(config, timestamp, column_config)
        if compact_type in {"uuid", "uniqueidentifier"}:
            return self.generate_uuid_value()
        if compact_type in {
            "numeric",
            "number",
            "float",
            "double",
            "decimal",
            "real",
            "doubleprecision",
        }:
            return self.generate_numeric_value(field_name, config, column_config)
        if compact_type in {
            "integer",
            "int",
            "smallint",
            "bigint",
            "tinyint",
            "int2",
            "int4",
            "int8",
            "serial",
            "bigserial",
        }:
            return int(self.generate_numeric_value(field_name, config, column_config))
        if compact_type in {"boolean", "bool", "bit"}:
            return self.generate_boolean_value(column_config.get("true_probability"))
        if compact_type in {"categorical", "category", "enum"}:
            return self.generate_categorical_value(field_name, config, column_config)

        return self.generate_string_value()

    def generate_record(
        self,
        output_fields: list[str],
        schema: dict[str, Any],
        config: dict[str, Any],
        timestamp: datetime | None = None,
        column_configs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        range_field_mapping = schema.get("range_field_mapping", {})
        output_column_types = schema.get("output_column_types", {})
        column_configs = column_configs or {}
        use_rule_defaults = not bool(column_configs)

        return {
            field_name: self.generate_value(
                field_name,
                self.detect_column_type(
                    field_name,
                    range_field_mapping,
                    output_column_types,
                    column_configs.get(field_name, {}).get("type")
                    if isinstance(column_configs.get(field_name), dict)
                    else None,
                ),
                config,
                timestamp,
                column_configs.get(field_name, {})
                if isinstance(column_configs.get(field_name), dict)
                else None,
                use_rule_defaults,
            )
            for field_name in output_fields
        }

    def generate_numeric_value(
        self,
        field_name: str,
        config: dict[str, Any],
        column_config: dict[str, Any] | None = None,
    ) -> float:
        schema = config.get("schema", {})
        defaults = config.get("rules", {}).get("defaults", {}) if not column_config else {}
        range_config = schema.get("range_field_mapping", {}).get(field_name, {})
        column_config = column_config or {}

        min_value = column_config.get("min")
        max_value = column_config.get("max")

        if min_value is None:
            min_value = defaults.get(range_config.get("min"), defaults.get("min_value", 0))
        if max_value is None:
            max_value = defaults.get(range_config.get("max"), defaults.get("max_value", 100))

        if min_value is None:
            min_value = 0
        if max_value is None:
            max_value = 100
        if max_value < min_value:
            min_value, max_value = max_value, min_value

        return round(random.uniform(min_value, max_value), 2)

    def generate_string_value(self) -> str:
        if self.faker:
            return self.faker.word()
        return "".join(random.choices(string.ascii_letters, k=8))

    def generate_datetime_value(
        self,
        config: dict[str, Any],
        timestamp: datetime | None = None,
        column_config: dict[str, Any] | None = None,
    ) -> datetime:
        if timestamp is not None:
            return timestamp

        column_config = column_config or {}

        column_start = self._parse_datetime(column_config.get("min"))
        column_end = self._parse_datetime(column_config.get("max"))
        if column_start is not None or column_end is not None:
            if column_start is None:
                column_start = column_end
            if column_end is None:
                column_end = column_start
            if column_start > column_end:
                column_start, column_end = column_end, column_start

            total_seconds = int((column_end - column_start).total_seconds())
            return column_start + timedelta(seconds=random.randint(0, max(total_seconds, 0)))

        general_config = config.get("general", {})
        start_time = self._parse_datetime(general_config.get("start_time"))
        end_time = self._parse_datetime(general_config.get("end_time"))

        if start_time is None or end_time is None:
            duration_hours_raw = general_config.get("duration_hours", 1)
            try:
                duration_hours = int(duration_hours_raw) if duration_hours_raw is not None else 1
            except (TypeError, ValueError):
                duration_hours = 1
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=duration_hours)
        if start_time > end_time:
            start_time, end_time = end_time, start_time

        total_seconds = int((end_time - start_time).total_seconds())
        return start_time + timedelta(seconds=random.randint(0, max(total_seconds, 0)))

    def generate_uuid_value(self) -> str:
        return str(uuid.uuid4())

    def generate_boolean_value(self, true_probability: float | None = None) -> bool:
        if true_probability is None:
            return random.choice([True, False])

        try:
            probability = float(true_probability)
        except (TypeError, ValueError):
            probability = 0.5

        probability = min(max(probability, 0.0), 1.0)
        return random.random() < probability

    def generate_categorical_value(
        self,
        field_name: str,
        config: dict[str, Any],
        column_config: dict[str, Any] | None = None,
    ) -> Any:
        column_config = column_config or {}
        explicit_values = column_config.get("values")
        if isinstance(explicit_values, list) and explicit_values:
            return self._pick_weighted_value(
                explicit_values,
                column_config.get("values_probabilities"),
            )

        schema = config.get("schema", {})
        categorical_values = schema.get("categorical_values", {})
        values = categorical_values.get(field_name)
        if values:
            return random.choice(values)
        return self.generate_string_value()

    def _pick_weighted_value(self, values: list[Any], probabilities: Any) -> Any:
        if not isinstance(probabilities, list) or len(probabilities) != len(values):
            return random.choice(values)

        try:
            normalized_weights = [float(weight) for weight in probabilities]
        except (TypeError, ValueError):
            return random.choice(values)

        if any(weight < 0 for weight in normalized_weights):
            return random.choice(values)

        total_weight = sum(normalized_weights)
        if total_weight <= 0:
            return random.choice(values)

        return random.choices(values, weights=normalized_weights, k=1)[0]

    def _should_return_null(self, column_config: dict[str, Any]) -> bool:
        nullable = column_config.get("nullable")
        if nullable is False:
            return False

        null_probability = column_config.get("null_probability")
        if null_probability is None:
            return False

        try:
            probability = float(null_probability)
        except (TypeError, ValueError):
            return False

        probability = min(max(probability, 0.0), 1.0)
        return random.random() < probability

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            try:
                return datetime.combine(value, datetime.min.time())
            except Exception:
                return None
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _generate_semantic_string(self, semantic: Any) -> str | None:
        if not isinstance(semantic, str) or not semantic.strip() or not self.faker:
            return None

        normalized = semantic.strip().lower()
        if normalized in {"first_name", "firstname", "given_name"}:
            return self.faker.first_name()
        if normalized in {"last_name", "lastname", "surname", "family_name"}:
            return self.faker.last_name()
        if normalized in {"full_name", "name"}:
            return self.faker.name()
        if normalized in {"email", "email_address"}:
            return self.faker.email()
        if normalized in {"username", "user_name", "login"}:
            return self.faker.user_name()
        if normalized in {"company", "organization", "organisation"}:
            return self.faker.company()
        if normalized in {"country", "country_name"}:
            return self.faker.country()
        if normalized in {"country_code", "iso_country_code"}:
            return self.faker.country_code(representation="alpha-2")

        return None

    def _get_default_value(self, field_name: str, defaults: dict[str, Any]) -> Any:
        if field_name in defaults:
            return defaults[field_name]

        # Support case-insensitive field default matching (e.g., Id vs id).
        field_name_lower = field_name.lower()
        for key, value in defaults.items():
            if isinstance(key, str) and key.lower() == field_name_lower:
                return value

        return None
