from app.transaction_loader import TRANSACTIONS


class Menu:
    def show(self):
        print("\n==============================")
        print(" Workload benchmark T1-T6")
        print("==============================")
        print(" 1. Run one transaction")
        print(" 2. Run whole workload (T1-T6)")
        print(" 0. Exit")

    def ask_option(self):
        while True:
            answer = input("Choose option: ").strip()
            if answer in ["0", "1", "2"]:
                return answer
            print("Unknown option, type 0, 1 or 2.")

    def ask_transaction(self):
        print()
        for name in TRANSACTIONS:
            print(f" {name}  {TRANSACTIONS[name]}")
        while True:
            answer = input("Transaction (e.g. T3 or 3): ").strip().upper()
            if not answer.startswith("T"):
                answer = "T" + answer
            if answer in TRANSACTIONS:
                return answer
            print("No such transaction.")

    def ask_repetitions(self):
        while True:
            answer = input("Number of runs [1]: ").strip()
            if answer == "":
                return 1
            if answer.isdigit() and int(answer) >= 1:
                return int(answer)
            print("Type a whole number greater than 0.")
