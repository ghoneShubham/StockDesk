import uuid

from .logging_filters import set_current_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """
    Assigns a unique id to every incoming request so that every log line
    produced while handling it can be correlated, and so that error reports
    can be tied back to a single user action.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        request.request_id = request_id
        set_current_request_id(request_id)
        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id
        return response
