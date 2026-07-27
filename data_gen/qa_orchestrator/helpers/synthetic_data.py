from qa_orchestrator.services.syn_dataloader.load_data import run_synthetic
import asyncio
class SyntheticDataGenerator:
    """
    Entrypoint for synthetic data generator
    """

    async def generate_data(self):
        """Generates a dummy product."""

        ### run with dummy synthetic data generated based on generic-config + override defined
        data_config = {"overrides": {
        "output": {
            "db_config": {
                "table_name": "my_synthetic_table1"
            }
        },
        "schema": {
            "output_fields": ["equipment_id", "event_timestamp", "temperature", "value", 'tag_name'],
            "output_column_types": {
                "equipment_id": "string",
                "event_timestamp": "datetime",
                "temperature": "numeric",
                "tag_name": "string"
            },
            "range_field_mapping": {
                "temperature": {"min": "min_value", "max": "max_value"}
            }
        },
        "rules": {
            "defaults": {
                "min_value": 0,
                "max_value": 100,
                "record_count": 100
                }
            }
        }
        }
        return await run_synthetic(data_config)


if __name__ == "__main__":
    synd = SyntheticDataGenerator()
    asyncio.run(synd.generate_data())

#### Plant_Opti specific data generation, historian_config, eot_config YAML files will move out of this repo, used here for testing
    ## qb/historian_entity.yaml and qb/eot_entity.yaml will also move out
    # current_time = datetime.now(tz= timezone.utc)
    
    # historian_config_file = os.path.join(os.path.dirname(__file__),'historian_config.yaml')
    # eot_config_file = os.path.join(os.path.dirname(__file__),'eot_config.yaml')

    # data_config = data_sources_config = {
    #     "qb": {
    #         "historian": {
    #             "config_file":historian_config_file,
    #             "overrides": {
    #                 "general": {
    #                     "start_time": current_time + timedelta(hours=-14),
    #                     "end_time": current_time
    #                 },
    #                 "rules": {
    #                     "entity_file": "qb/historian_entity.yaml"
    #                 }
    #             }
    #         },
    #         "eot": {
    #             "config_file": eot_config_file,
    #             "overrides": {
    #                 "general": {
    #                     "start_time": current_time + timedelta(hours=-3),
    #                     "end_time": current_time + timedelta(hours=1),
    #                     "default_frequency": "1min"
    #                 },
    #                 "rules": {
    #                     "entity_file": "qb/eot_entity_actual.yaml"
    #                 }
    #             }
    #         }
    #     }
    # }