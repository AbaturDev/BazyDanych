import os

SQLPLUS_COMMANDS = ["SET TIMING", "SET LINESIZE", "SET PAGESIZE"]

class Statement:
    def __init__(self, transaction, name, sql):
        self.transaction = transaction
        self.name = name
        self.sql = sql

    def returns_rows(self):
        first_word = self.sql.split()[0].upper()
        return first_word == "SELECT" or first_word == "WITH"


class TransactionLoader:
    def __init__(self, workload_folder):
        self.workload_folder = workload_folder

    def load(self, transaction):
        path = os.path.join(self.workload_folder, transaction.lower() + ".sql")
        with open(path, encoding="utf-8") as file:
            lines = file.readlines()

        statements = []
        current_lines = []
        current_name = transaction

        for line in lines:
            text = line.strip()

            if self.is_sqlplus_command(text):
                continue

            # Empty lines between statements are not part of any statement
            if text == "" and len(current_lines) == 0:
                continue

            # A comment before a statement may give it a name: "-- T4.1 Nagłówki zamówień"
            if text.startswith("--") and len(current_lines) == 0:
                words = text[2:].split()
                if len(words) > 0 and words[0].startswith(transaction + "."):
                    current_name = words[0]
                continue

            current_lines.append(line.rstrip())

            # ";" at the end of a line closes the statement
            if text.endswith(";"):
                sql = "\n".join(current_lines).strip()
                sql = sql[:-1].strip()   # Oracle does not accept the final ";"

                if sql.upper() == "ROLLBACK":
                    current_name = transaction + " ROLLBACK"

                statements.append(Statement(transaction, current_name, sql))
                current_lines = []
                current_name = transaction

        # The last statement in a file may have no ";"
        sql = "\n".join(current_lines).strip()
        if sql != "":
            statements.append(Statement(transaction, current_name, sql))

        return statements

    def is_sqlplus_command(self, text):
        for command in SQLPLUS_COMMANDS:
            if text.upper().startswith(command):
                return True
        return False
