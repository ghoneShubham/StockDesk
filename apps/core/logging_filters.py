import threading

_local = threading.local()


def set_current_request_id(request_id):
    _local.request_id = request_id


def get_current_request_id():
    return getattr(_local, "request_id", "-")


class RequestIDFilter:
    """Injects the current request's id into every log record for correlation."""

    def filter(self, record):
        record.request_id = get_current_request_id()
        return True
