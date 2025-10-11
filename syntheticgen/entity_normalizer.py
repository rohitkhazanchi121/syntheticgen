class EntityNormalizer:
    def __init__(self, entity_config, config):
        self.entity_config = entity_config
        self.config = config

    def normalize(self):
        entity = self.entity_config.get("entity", {})
        normalization_rules = self.config.get("filtering", {})
        excluse_entity = normalization_rules.get("exclude_entity", [])
        for ent in excluse_entity:
            if ent in entity:
                del entity[ent]
        override_entity = normalization_rules.get("entity_overrides", {})
        for ent, properties in override_entity.items():
            if ent in entity:
                entity[ent].update(properties)
        default_values = self.config["rules"].get("defaults", {})
        valid_defaults = {k: v for k, v in default_values.items() if v is not None}
        for ent, prop in entity.items():
            prop.update({k: v for k, v in valid_defaults.items() if prop.get(k) is None})
        return {"entity": entity}
