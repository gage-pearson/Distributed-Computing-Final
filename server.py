import threading

import rpyc
from rpyc.utils.server import ThreadedServer


patients = {
    "P1001": {
        "name": "Jordan Poole",
        "age": 27,
        "phone": "555-0100",
        "address": "10 Sample Street",
        "department": "Cardiology",
        "medical_history": ["high blood pressure"],
        "diagnosis": "Hypertension",
        "test_results": {"Blood test": {"blood_pressure": "150/90 mmHg"}},
        "version": 1
    },
    "P1002": {
        "name": "Taylor Swift",
        "age": 36,
        "phone": "555-0101",
        "address": "20 Sample Street",
        "department": "Neurology",
        "medical_history": ["migraine headaches"],
        "diagnosis": "Migraine",
        "test_results": {"MRI": {"brain_scan": "no abnormalities found"}},
        "version": 1
    }
}


lock = threading.Lock()


class PatientRecords(rpyc.Service):
    def exposed_get_patient(self, patient_id):
        with lock:
            record = patients.get(patient_id)

            if record is None:
                return ("not found",)

            return (
                "ok",
                record["name"],
                record["phone"],
                record["address"],
                record["department"],
                record["medical_history"],
                record["diagnosis"],
                record["test_results"],
                record["version"]
            )

    def exposed_update_patient(self, patient_id, expected_version, field, new_value):
        if field not in ("phone", "address"):
            return "invalid field"

        if not isinstance(new_value, str) or not new_value.strip():
            return "invalid value"

        with lock:
            record = patients.get(patient_id)

            if record is None:
                return "not found"

            if expected_version != record["version"]:
                return "conflict"

            record[field] = new_value.strip()
            record["version"] += 1
            return "ok"
    
    def exposed_add_patient(self, patient_id, name, phone, address, department, medical_history, diagnosis, test_results):
        patient_id = patient_id.strip().upper()
        name = name.strip()
        phone = phone.strip()
        address = address.strip()
        department = department.strip()
        medical_history = [history.strip() for history in medical_history]
        diagnosis = diagnosis.strip()
        test_results = {test: {key: value for key, value in results.items()} for test, results in test_results.items()}

        if not patient_id or not name or not phone or not address:
            return "invalid value"

        with lock:
            if patient_id in patients:
                return "already exists"

            patients[patient_id] = {
                "name": name,
                "phone": phone,
                "address": address,
                "department": department,
                "medical_history": medical_history,
                "diagnosis": diagnosis,
                "test_results": test_results,
                "version": 1
            }

            return "ok"


if __name__ == "__main__":
    server = ThreadedServer(PatientRecords, hostname="127.0.0.1", port=55555)
    print("Server running on 127.0.0.1:55555")
    server.start()