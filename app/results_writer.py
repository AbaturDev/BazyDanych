import csv
import os

COLUMNS = ["seria", "przebieg", "transakcja", "instrukcja", "czas_ms", "wiersze", "plan_hash"]


class ResultsWriter:
    def __init__(self, path):
        self.path = path

        folder = os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)

        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow(COLUMNS)

    def write(self, series, run_number, results):
        with open(self.path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, delimiter=";")
            for result in results:
                writer.writerow([
                    series,
                    run_number,
                    result.statement.transaction,
                    result.statement.name,
                    round(result.elapsed_ms, 1),
                    result.rows,
                    "",   # plan_hash - filled by person B in step 8
                ])
