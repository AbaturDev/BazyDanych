import os


class Config:
    def __init__(self):
        values = self.read_env_file()

        self.app_user = values["APP_USER"]
        self.app_password = values["APP_USER_PASSWORD"]
        self.admin_password = values["ORACLE_PASSWORD"]
        self.dsn = "127.0.0.1:1521/FREEPDB1"
        self.workload_folder = os.path.join("db", "scripts", "workload")
        self.results_file = os.path.join("app", "wyniki", "pomiary.csv")

    def read_env_file(self):
        values = {}
        with open(".env", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line == "" or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return values
