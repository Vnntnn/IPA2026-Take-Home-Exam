"""Part 4 student implementation."""

import json

import logging

import os

from concurrent.futures import ThreadPoolExecutor

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from tempfile import TemporaryDirectory

from app.integration import process_request

from app.webex_client import WEBEX_API_BASE, WebexClient

log = logging.getLogger(__name__)

MAX_BODY = 1_000_000

class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor or process_request

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None
        if event.get('resource') != 'messages' or event.get('event') != 'created':
            return None
        data = event.get('data')
        message_id = data.get('id') if isinstance(data, dict) else None
        if not message_id or not isinstance(message_id, str):
            return None
        if data.get('personId') == self.bot_person_id:
            return None

        message = self.client.get_message(message_id)
        room_id = message.get('roomId')
        if not room_id or message.get('personId') == self.bot_person_id:
            return None

        mentioned = message.get('mentionedPeople')
        files = message.get('files') or []
        try:
            if len(files) > 1:
                result = {'status': 'error', 'result': 'multiple_attachments'}
            elif files:
                with TemporaryDirectory() as tmp:
                    path = Path(tmp) / 'request.yaml'
                    path.write_bytes(self.client.download_file(files[0]))
                    result = self.processor(mentioned, path, self.bot_person_id)
            else:
                result = self.processor(mentioned, None, self.bot_person_id)
        except Exception:
            log.exception('request failed')
            result = {'status': 'error', 'result': 'backend_failed'}

        self.client.send_message(room_id, json.dumps(result))
        return result

def make_http_handler(submit_event):
    def reply(handler, code, body):
        payload = json.dumps(body).encode()
        handler.send_response(code)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split('?')[0] == '/health':
                reply(self, 200, {'status': 'ok', 'result': 'healthy'})
            else:
                reply(self, 404, {'status': 'error', 'result': 'not_found'})

        def do_POST(self):
            if self.path.split('?')[0] != '/webhook':
                reply(self, 404, {'status': 'error', 'result': 'not_found'})
                return
            invalid = {'status': 'error', 'result': 'invalid_event'}
            try:
                length = int(self.headers.get('Content-Length', ''))
            except ValueError:
                length = 0
            if not 1 <= length <= MAX_BODY:
                # Drain the body so the client sees the 400, not a reset.
                remaining = min(max(length, 0), 10 * MAX_BODY)
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                self.close_connection = True
                reply(self, 400, invalid)
                return
            try:
                event = json.loads(self.rfile.read(length))
            except ValueError:  # includes bad UTF-8 and bad JSON
                event = None
            if not isinstance(event, dict):
                reply(self, 400, invalid)
                return
            submit_event(event)
            reply(self, 200, {'status': 'ok', 'result': 'accepted'})

        def log_message(self, format, *args):
            log.info('%s - %s', self.address_string(), format % args)

    return Handler

def main():
    logging.basicConfig(level=logging.INFO)
    client = WebexClient()
    handler = WebexEventHandler(client, client.get_person_id())
    # One worker: router changes must never overlap.
    executor = ThreadPoolExecutor(max_workers=1)

    def process(event):
        try:
            handler.handle_event(event)
        except Exception:
            log.exception('event failed')

    server = ThreadingHTTPServer(
        (os.environ.get('WEBHOOK_HOST', '0.0.0.0'),
         int(os.environ.get('WEBHOOK_PORT', '8000'))),
        make_http_handler(lambda event: executor.submit(process, event)),
    )
    server.serve_forever()

if __name__ == "__main__":
    main()
