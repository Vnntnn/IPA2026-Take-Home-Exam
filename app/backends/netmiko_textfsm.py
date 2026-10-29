import re

from netmiko import ConnectHandler
from ntc_templates.parse import parse_output
from textfsm.parser import TextFSMError

from app.backends.common import (
    TIMEOUT,
    check_name,
    classify,
    credentials,
    error,
    found,
    not_found,
)


def _connect(router):
    user, password = credentials()
    return ConnectHandler(
        device_type="cisco_ios", host=router, username=user, password=password,
        conn_timeout=TIMEOUT, auth_timeout=TIMEOUT, banner_timeout=TIMEOUT,
    )


def _records(command, output):
    """TextFSM records; [] when IOS reports '%' (e.g. the interface is gone)."""
    if "%" in output or not output.strip():
        return []
    try:
        return parse_output(platform="cisco_ios", command=command, data=output)
    except TextFSMError as exc:
        raise ValueError(f"TextFSM could not parse {command!r}") from exc


def _collect(conn, interface_name):
    check_name(interface_name)
    ip_cmd = f"show ip interface {interface_name}"
    desc_cmd = "show interfaces description"
    ip_info = _records(ip_cmd, conn.send_command(ip_cmd))
    descriptions = _records(desc_cmd, conn.send_command(desc_cmd))
    return ip_info, descriptions


def _netmiko_get(router, interface_name):
    with _connect(router) as conn:
        return _collect(conn, interface_name)


def _netmiko_delete(router, interface_name):
    with _connect(router) as conn:
        if _normalize(interface_name, *_collect(conn, interface_name)) is None:
            return "not_found"
        conn.send_config_set([f"no interface {interface_name}"])
        if _normalize(interface_name, *_collect(conn, interface_name)) is not None:
            raise RuntimeError("interface still present after delete")
        return "deleted"


def _split(name):
    match = re.match(r"([A-Za-z-]+)\s*(.*)", name.strip())
    return (match.group(1).lower(), match.group(2)) if match else ("", name)


def _same(a, b):
    """True for Loopback123 vs Lo123 (IOS abbreviates in some commands)."""
    (pa, ra), (pb, rb) = _split(a), _split(b)
    return ra == rb and (pa.startswith(pb) or pb.startswith(pa))


def _first(value):
    return value[0] if isinstance(value, list) else value


def _normalize(interface_name, ip_info, descriptions):
    ip = next((r for r in ip_info if _same(r.get("interface", ""), interface_name)), None)
    desc = next((r for r in descriptions if _same(r.get("port", ""), interface_name)), None)
    if ip is None and desc is None:
        return None

    ipv4 = None
    if ip and ip.get("ip_address") and ip.get("prefix_length"):
        ipv4 = f"{_first(ip['ip_address'])}/{_first(ip['prefix_length'])}"
    if ip:
        down = "administratively down" in str(ip.get("link_status", "")).lower()
    else:
        down = "admin" in str(desc.get("status", "")).lower()
    description = (desc.get("description") if desc else None) or ""

    return {
        "name": interface_name,
        "ipv4": ipv4,
        "description": description.strip() or None,
        "admin_state": "down" if down else "up",
    }


def get_interface_state(
    router,
    interface_name,
    netmiko_get=None,
):
    """Return normalized interface status using Netmiko + TextFSM."""
    try:
        ip_info, descriptions = (netmiko_get or _netmiko_get)(router, interface_name)
        interface = _normalize(interface_name, ip_info, descriptions)
        return not_found() if interface is None else found(interface)
    except Exception as exc:
        return error(classify(exc))


def delete_interface(
    router,
    interface_name,
    netmiko_delete=None,
):
    """Delete an interface using Netmiko."""
    try:
        outcome = (netmiko_delete or _netmiko_delete)(router, interface_name)
    except Exception as exc:
        return error(classify(exc))
    if outcome == "deleted":
        return {"status": "ok", "result": "deleted"}
    if outcome == "not_found":
        return not_found()
    return error("backend_failed")
