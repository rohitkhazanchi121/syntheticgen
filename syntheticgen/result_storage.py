import os
import pandas as pd
from sqlalchemy import create_engine


class ResultStorage:
    def __init__(self, config):
        self.config = config

    def store(self, records):
        if not records:
            print("No records to store.")
            return
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        config_output = self.config.get("output", {})
        if config_output.get("sink") == "db":
            db_conf = config_output.get("db_config")
            required_keys = ["type", "host_env", "database_env", "port_env", "user_env", "password_env"]
            for key in required_keys:
                if key not in db_conf:
                    raise ValueError(f"Missing '{key}' in 'db_config'")
            db_type = db_conf.get("type")
            if db_type == "postgres":
                database_url = f"postgresql+psycopg://{os.getenv(db_conf.get('user_env'))}:{os.getenv(db_conf.get('password_env'))}@{os.getenv(db_conf.get('host_env'))}:{os.getenv(db_conf.get('port_env'))}/{os.getenv(db_conf.get('database_env'))}"
            engine = create_engine(database_url)
            with engine.begin() as connection:
                df.to_sql(db_conf.get("table_name"), con=connection, if_exists="replace", index=False)
                print(
                    f"Data successfully written to {db_conf.get('table_name')} table with {len(df)} records in {db_type} database."
                )
            return True
        else:
            print("No output configured, skipping storage returning dataframe")
            return df
