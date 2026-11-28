from app.benchmark import Benchmark
from app.config import Config
from app.database_preparation import DatabasePreparation
from app.menu import Menu
from app.results_writer import ResultsWriter
from app.transaction_loader import TRANSACTIONS, TransactionLoader


def main():
    config = Config()
    loader = TransactionLoader(config.workload_folder)
    preparation = DatabasePreparation(config)
    results_writer = ResultsWriter(config.results_file)
    benchmark = Benchmark(config, loader, preparation, results_writer)
    menu = Menu()

    while True:
        menu.show()
        option = menu.ask_option()

        if option == "0":
            break

        if option == "1":
            transaction = menu.ask_transaction()
            repetitions = menu.ask_repetitions()
            benchmark.run([transaction], repetitions)

        if option == "2":
            repetitions = menu.ask_repetitions()
            benchmark.run(list(TRANSACTIONS), repetitions)


try:
    main()
except KeyboardInterrupt:
    # Ctrl+C: uncommitted changes are rolled back when the connection closes
    print("\nInterrupted.")
