"""Point the bot's Webex webhooks at a tunnel URL (re-run when the URL changes).

    WEBEX_BOT_TOKEN=... PYTHONPATH=. python scripts/register_webhook.py https://xxx.trycloudflare.com

Replaces all of this bot's webhooks with one messages/created webhook per room
in ROOMS (the bot must already be a member of both).
"""

import sys

from app.webex_client import WEBEX_API_BASE, WebexClient

ROOMS = ("IPA2026", "IPA2026 Exam Room")


def main(public_url):
    client = WebexClient()
    api = lambda method, path, **kw: client.session.request(  # noqa: E731
        method, f"{WEBEX_API_BASE}{path}", headers=client.headers, timeout=10, **kw
    )

    rooms = api("GET", "/rooms", params={"max": 1000}).json()["items"]
    room_ids = {r["title"]: r["id"] for r in rooms if r["title"] in ROOMS}
    missing = [t for t in ROOMS if t not in room_ids]
    if missing:
        sys.exit(f"bot is not a member of: {missing}")

    for hook in api("GET", "/webhooks").json()["items"]:
        api("DELETE", f"/webhooks/{hook['id']}").raise_for_status()

    for title, room_id in room_ids.items():
        response = api("POST", "/webhooks", json={
            "name": f"ipa2026 {title}",
            "targetUrl": public_url.rstrip("/") + "/webhook",
            "resource": "messages",
            "event": "created",
            "filter": f"roomId={room_id}",
        })
        response.raise_for_status()
        print(f"registered {title}: {response.json()['id']}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
        sys.exit(__doc__)
    main(sys.argv[1])
