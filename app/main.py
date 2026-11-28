import oracledb

from app.config import Config
from app.transaction_loader import TransactionLoader
from app.transaction_runner import TransactionRunner

TRANSACTIONS = ["T1", "T2", "T3", "T4", "T5", "T6"]


def main():
    config = Config()
    loader = TransactionLoader(config.workload_folder)

    connection = oracledb.connect(user=config.app_user,
                                  password=config.app_password,
                                  dsn=config.dsn)
    try:
        runner = TransactionRunner(connection)
        workload_ms = 0

        for transaction in TRANSACTIONS:
            print(transaction)
            statements = loader.load(transaction)
            transaction_ms = runner.run(statements)
            workload_ms = workload_ms + transaction_ms
            print(f"  {transaction} total: {transaction_ms:.1f} ms\n")

        print(f"Whole workload: {workload_ms:.1f} ms")
    finally:
        connection.rollback()
        connection.close()


main()
