import time


class StatementResult:
    def __init__(self, statement, elapsed_ms, rows):
        self.statement = statement
        self.elapsed_ms = elapsed_ms
        self.rows = rows


class TransactionRunner:
    def __init__(self, connection):
        self.connection = connection

    def run(self, statements):
        cursor = self.connection.cursor()
        results = []

        for statement in statements:
            start = time.perf_counter()

            cursor.execute(statement.sql)
            if statement.returns_rows():
                rows = len(cursor.fetchall())
            else:
                rows = cursor.rowcount

            elapsed_ms = (time.perf_counter() - start) * 1000

            if statement.is_rollback():
                print(f"  {statement.name:<12} {elapsed_ms:10.1f} ms   (not counted)")
                continue

            results.append(StatementResult(statement, elapsed_ms, rows))
            print(f"  {statement.name:<12} {elapsed_ms:10.1f} ms   rows: {rows}")

        cursor.close()
        return results
