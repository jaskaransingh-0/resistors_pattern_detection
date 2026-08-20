from queue import Queue
import uuid

uuid_queue = Queue()


def generate_uuid() -> str:
    # Producer
    scan_uuid = str(uuid.uuid4())
    uuid_queue.put(scan_uuid)

    return scan_uuid


def get_current_uuid() -> str:
    # Consumer thread
    current_uuid = uuid_queue.get()
    return current_uuid