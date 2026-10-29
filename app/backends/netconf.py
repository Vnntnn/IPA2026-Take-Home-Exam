import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from ncclient import manager

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

NS = {
    "if": "urn:ietf:params:xml:ns:yang:ietf-interfaces",
    "ip": "urn:ietf:params:xml:ns:yang:ietf-ip",
}


def _connect(router):
    user, password = credentials()
    return manager.connect(
        host=router, port=830, username=user, password=password,
        hostkey_verify=False, allow_agent=False, look_for_keys=False,
        timeout=TIMEOUT,
    )


def _get_config(router, filter_xml):
    with _connect(router) as m:
        return m.get_config(source="running", filter=("subtree", filter_xml)).data_xml


def _edit_config(router, config_xml):
    with _connect(router) as m:
        m.edit_config(target="running", config=config_xml)


def _normalize(node):
    address = node.find("ip:ipv4/ip:address", NS)
    ipv4 = None
    if address is not None:
        mask = address.findtext("ip:netmask", namespaces=NS) or address.findtext(
            "ip:prefix-length", namespaces=NS
        )
        ipv4 = cidr(address.findtext("ip:ip", namespaces=NS).strip(), mask.strip())
    enabled = (node.findtext("if:enabled", namespaces=NS) or "true").strip().lower()
    description = (node.findtext("if:description", namespaces=NS) or "").strip()
    return {
        "name": node.findtext("if:name", namespaces=NS).strip(),
        "ipv4": ipv4,
        "description": description or None,
        "admin_state": "down" if enabled == "false" else "up",
    }


def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    netconf_get_config = netconf_get_config or _get_config
    filter_xml = (
        f'<interfaces xmlns="{NS["if"]}"><interface>'
        f"<name>{escape(interface_name)}</name>"
        "</interface></interfaces>"
    )
    try:
        root = ET.fromstring(netconf_get_config(router, filter_xml))
        for node in root.iterfind(".//if:interface", NS):
            if (node.findtext("if:name", namespaces=NS) or "").strip() == interface_name:
                return found(_normalize(node))
        return not_found()
    except Exception as exc:
        return error(classify(exc))


def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    return planning.plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, netconf_get_config),
    )


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    netconf_edit_config = netconf_edit_config or _edit_config
    try:
        number = loopback_number(desired_interface["name"])
        address = desired_interface["ipv4"].split("/")[0]
        shutdown = "<shutdown/>" if desired_interface["admin_state"] == "down" else ""
        config_xml = (
            '<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" '
            'xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">'
            '<native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">'
            "<interface>"
            '<Loopback nc:operation="replace">'
            f"<name>{number}</name>"
            f"<description>{escape(desired_interface['description'])}</description>"
            "<ip><address><primary>"
            f"<address>{address}</address>"
            f"<mask>{netmask(desired_interface['ipv4'])}</mask>"
            "</primary></address></ip>"
            f"{shutdown}"
            "</Loopback></interface></native></config>"
        )
        netconf_edit_config(router, config_xml)
        return {"status": "ok", "result": "applied"}
    except Exception as exc:
        return error(classify(exc))
