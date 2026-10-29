import yaml

ROUTERS = {
    "10.0.29.101",
    "10.0.29.102",
    "10.0.29.103",
    "10.0.29.104",
    "10.0.29.105",
}

ACTIONS = {
    "restconf": {"status", "plan", "apply"},
    "netconf": {"status", "plan", "apply"},
    "ansible": {"apply"},
    "netmiko-textfsm": {"status", "delete"},
}


def _error(result):
    return {"status": "error", "result": result}


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    if not isinstance(data, dict):
        return _error("invalid_yaml")

    version = data.get("version")
    if type(version) is not int or version != 1:  # bool is an int subclass
        return _error("invalid_version")

    if _blank(data.get("router")):
        return _error("missing_router")
    if not isinstance(data["router"], str) or data["router"] not in ROUTERS:
        return _error("invalid_router")

    if _blank(data.get("method")):
        return _error("missing_method")
    method = data["method"]
    if not isinstance(method, str) or method not in ACTIONS:
        return _error("invalid_method")

    if _blank(data.get("action")):
        return _error("missing_action")
    action = data["action"]
    if not isinstance(action, str) or action not in ACTIONS[method]:
        return _error("invalid_action")

    desired = data.get("desired")
    if not isinstance(desired, dict):
        return _error("missing_desired")
    interface = desired.get("interface")
    if not isinstance(interface, dict):
        return _error("missing_interface")
    name = interface.get("name")
    if not isinstance(name, str) or not name.strip():
        return _error("missing_interface_name")

    if action in ("plan", "apply"):
        for field in ("ipv4", "description", "admin_state"):
            if _blank(interface.get(field)):
                return _error(f"missing_{field}")
        if interface["admin_state"] not in ("up", "down"):
            return _error("invalid_admin_state")

    return {"status": "ok", "result": "accepted"}


def load_request_file(path):
    """Return (data, None) or (None, error_response)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError):
        return None, _error("invalid_yaml")
    if not isinstance(data, dict):
        return None, _error("invalid_yaml")
    return data, None


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    data, err = load_request_file(path)
    return err or validate_request(data)
