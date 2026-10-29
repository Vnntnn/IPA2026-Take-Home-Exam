"""Part 4 student implementation."""

from app.core import load_request_file, validate_request
from app.dispatcher import dispatch_request

from app.request_handler import validate_webex_envelope

def process_request(mentioned_people, attachment_path, bot_person_id):
    error = validate_webex_envelope(mentioned_people, attachment_path, bot_person_id)
    if error:
        return error
    data, error = load_request_file(attachment_path)
    if error:
        return error
    verdict = validate_request(data)
    if verdict["status"] != "ok":
        return verdict
    return dispatch_request(data)
