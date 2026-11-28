import time


class TransactionRunner:
    def __init__(self, connection):
        self.connection = connection

    def run(self, statements):
        cursor = self.connection.cursor()
        total_ms = 0

        for statement in statements:
            start = time.perf_counter()

            cursor.execute(statement.sql)
            if statement.returns_rows():
                rows = len(cursor.fetchall())
            else:
                rows = cursor.rowcount

            elapsed_ms = (time.perf_counter() - start) * 1000
            total_ms = total_ms + elapsed_ms

            print(f"  {statement.name:<12} {elapsed_ms:10.1f} ms   rows: {rows}")

        cursor.close()
        return total_ms
