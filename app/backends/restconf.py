from urllib.parse import quote

import requests

from app.backends import planning
from app.backends.common import (
    TIMEOUT,
    cidr,
    classify,
    credentials,
    error,
    found,
    loopback_number,
    netmask,
    not_found,
)

HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}


def _http_get(url):
    return requests.get(
        url, headers=HEADERS, auth=credentials(), verify=False, timeout=TIMEOUT
    )


def _http_put(url, json):
    return requests.put(
        url, headers=HEADERS, auth=credentials(), json=json,
        verify=False, timeout=TIMEOUT,
    )


def _normalize(data):
    addresses = data.get("ietf-ip:ipv4", {}).get("address") or []
    ipv4 = None
    if addresses:
        first = addresses[0]
        ipv4 = cidr(first["ip"], first.get("netmask") or first["prefix-length"])
    return {
        "name": data["name"],
        "ipv4": ipv4,
        "description": data.get("description"),
        "admin_state": "up" if data.get("enabled", True) else "down",
    }


def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    http_get = http_get or _http_get
    url = (
        f"https://{router}/restconf/data/ietf-interfaces:interfaces/"
        f"interface={quote(interface_name, safe='')}"
    )
    try:
        response = http_get(url)
        code = response.status_code
        if code in (401, 403):
            return error("authentication_failed")
        if code in (204, 404):
            return not_found()
        if code != 200:
            return error("backend_failed")
        return found(_normalize(response.json()["ietf-interfaces:interface"]))
    except Exception as exc:
        return error(classify(exc))


def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    return planning.plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, http_get),
    )


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    http_put = http_put or _http_put
    try:
        number = loopback_number(desired_interface["name"])
        primary = {
            "address": desired_interface["ipv4"].split("/")[0],
            "mask": netmask(desired_interface["ipv4"]),
        }
        payload = {
            "name": number,
            "description": desired_interface["description"],
            "ip": {"address": {"primary": primary}},
        }
        if desired_interface["admin_state"] == "down":
            payload["shutdown"] = [None]
        response = http_put(
            f"https://{router}/restconf/data/"
            f"Cisco-IOS-XE-native:native/interface/Loopback={number}",
            json={"Cisco-IOS-XE-native:Loopback": payload},
        )
        code = response.status_code
        if code in (200, 201, 204):
            return {"status": "ok", "result": "applied"}
        if code in (401, 403):
            return error("authentication_failed")
        return error("backend_failed")
    except Exception as exc:
        return error(classify(exc))
