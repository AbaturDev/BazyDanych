import oracledb

from app.transaction_runner import TransactionRunner


class Benchmark:
    def __init__(self, config, loader, preparation):
        self.config = config
        self.loader = loader
        self.preparation = preparation

    def run(self, transactions, repetitions):
        statements_by_transaction = {}
        for transaction in transactions:
            statements_by_transaction[transaction] = self.loader.load(transaction)

        run_totals = []
        for run_number in range(1, repetitions + 1):
            print(f"\n=== Run {run_number}/{repetitions} ===")
            self.preparation.prepare()
            total_ms = self.run_once(transactions, statements_by_transaction)
            run_totals.append(total_ms)
            print(f"Run {run_number} total: {total_ms:.1f} ms")

        print("\nSummary:")
        for index in range(len(run_totals)):
            print(f"  run {index + 1}: {run_totals[index]:10.1f} ms")

    def run_once(self, transactions, statements_by_transaction):
        # New connection for every run, so nothing is carried over from the previous one
        connection = oracledb.connect(user=self.config.app_user,
                                      password=self.config.app_password,
                                      dsn=self.config.dsn)
        try:
            runner = TransactionRunner(connection)
            total_ms = 0
            for transaction in transactions:
                print(transaction)
                transaction_ms = runner.run(statements_by_transaction[transaction])
                total_ms = total_ms + transaction_ms
                print(f"  {transaction} total: {transaction_ms:.1f} ms")
            return total_ms
        finally:
            connection.rollback()
            connection.close()
