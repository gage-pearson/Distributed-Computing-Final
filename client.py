import threading
import rpyc
import sys
import argparse




HOST = '127.0.0.1'
PORT = 55555
UPDATE_FIELDS = ['phone', 'address']
MAX_RETRIES = 10 # amount of attempts to update a record before giving up because of version conflicts.

class Client:
    def __init__(self):
        self.connection = rpyc.connect(HOST, PORT, config={"allow_public_attrs": True})

    def close(self):
        self.connection.close()

    def get_patient(self, patient_id):
        result = self.connection.root.get_patient(patient_id.strip().upper())
        if result[0] != "ok":
            return None
        name, phone, address, department, history, diagnosis, tests, version = result[1:]
       
        return {
            "name": name, "phone": phone, "address": address, "department": department,
            "medical_history": list(history), "diagnosis": diagnosis,
            "test_results": {test: {k: tests[test][k] for k in tests[test]} for test in tests},
            "version": version,
        }

    def update_patient(self, patient_id, field, new_value):
        for attempt in range(1, MAX_RETRIES + 1):
            record = self.get_patient(patient_id)
            if record is None:
                return "not found", attempt
            status = self.connection.root.update_patient(
                patient_id.strip().upper(), record["version"], field, new_value)
            if status != "conflict":
                return status, attempt
        return "conflict", MAX_RETRIES

    def add_patient(self, patient_id, name, phone, address, department,
                    medical_history, diagnosis, test_results):
        return self.connection.root.add_patient(patient_id, name, phone, address, department,
                                                medical_history, diagnosis, test_results)

def print_record(record):
    for key, value in record.items():
        label = key.replace("_", " ").capitalize()
        if key == "medical_history":
            value = ", ".join(value) or "none"
        elif key == "test_results":
            value = "; ".join(f"{test}: " + ", ".join(f"{k}={v}" for k, v in results.items())
                              for test, results in value.items()) or "none"
        print(f"  {label:<16} {value}")

def ask_new_patient():
    patient_id, name, phone, address, department = [
        input(f"{label}: ") for label in ("Patient ID", "Name", "Phone", "Address", "Department")]
    history = [h.strip() for h in input("Medical history (comma-separated): ").split(",") if h.strip()]
    diagnosis = input("Diagnosis: ")
    
    test_results = {}
    while True:
        test = input("Test name (blank to finish): ").strip()
        if not test:
            break
        pairs = input(f"{test} results (key=value, comma-separated): ").split(",")
        test_results[test] = {k.strip(): v.strip() for k, v in
                              (p.split("=", 1) for p in pairs if "=" in p)}
    return patient_id, name, phone, address, department, history, diagnosis, test_results

def run_interactive(department):
    client = Client()
    print(f"[{department}] Connected to {HOST}:{PORT}.")
    try:
        while True:
            choice = input("\n1) View  2) Update  3) Add  4) Quit: ").strip()
            if choice == "1":
                record = client.get_patient(input("Patient ID: "))
                print_record(record) if record else print("Patient not found.")
            elif choice == "2":
                patient_id = input("Patient ID: ")
                field = input(f"Field ({'/'.join(UPDATE_FIELDS)}): ").strip().lower()
                if field not in UPDATE_FIELDS:
                    print("Invalid field.")
                    continue
                status, attempts = client.update_patient(patient_id, field, input(f"New {field}: "))
                print(f"Update result: {status} (attempts: {attempts})")
            elif choice == "3":
                print("Add result:", client.add_patient(*ask_new_patient()))
            elif choice == "4":
                break
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        client.close()
        print("Connection closed.")

def run_test(patient_id, num_clients):
    checker = Client()
    before = checker.get_patient(patient_id)
    if before is None:
        sys.exit(f"Patient {patient_id} not found.")
    print("Starting record:")
    print_record(before)

    barrier = threading.Barrier(num_clients)  
    results = []
    results_lock = threading.Lock()

    def department(i):
        field = UPDATE_FIELDS[i % 2]
        value = f"555-{2000 + i}" if field == "phone" else f"{100 + i} Department {i + 1} Ave"
        client = Client()
        barrier.wait()
        client.get_patient(patient_id)  
        status, attempts = client.update_patient(patient_id, field, value)
        client.close()
        with results_lock:
            results.append((i + 1, field, value, status, attempts))

    threads = [threading.Thread(target=department, args=(i,)) for i in range(num_clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"\nResults from {num_clients} concurrent departments:")
    for num, field, value, status, attempts in sorted(results):
        print(f"  Department {num:<3} {field:<8} -> {value:<26} {status} (attempts: {attempts})")

    after = checker.get_patient(patient_id)
    checker.close()
    print("\nFinal record:")
    print_record(after)

    ok = [r for r in results if r[3] == "ok"]
    expected = before["version"] + len(ok)
    values_ok = all(after[f] in [r[2] for r in ok if r[1] == f]
                    for f in UPDATE_FIELDS if any(r[1] == f for r in ok))
    passed = after["version"] == expected and values_ok
    print(f"\nSuccessful updates: {len(ok)}/{num_clients}")
    print(f"Expected version: {expected}, actual: {after['version']}")
    print("Consistency check:", "PASSED" if passed else "FAILED")
    if not passed:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Patient records RPC client.")
    parser.add_argument("--department", default="Front Desk", help="department name")
    parser.add_argument("--test", action="store_true", help="run the concurrent update test")
    parser.add_argument("--patient", default="P1001", help="patient ID for the test")
    parser.add_argument("--clients", type=int, default=5, help="number of concurrent departments")
    args = parser.parse_args()

    try:
        if args.test:
            run_test(args.patient.strip().upper(), max(1, args.clients))
        else:
            run_interactive(args.department)
    except ConnectionRefusedError:
        sys.exit("Connection failed. Start server.py first.")

if __name__ == "__main__":
    main()
