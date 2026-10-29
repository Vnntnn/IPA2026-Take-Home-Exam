"""Part 4 student implementation."""

from app.backends import ansible, netconf, netmiko_textfsm, restconf

# (method, action) -> (backend module, function name, argument kind)
# The function is looked up at call time so tests can monkeypatch it.
ROUTES = {
    ("restconf", "status"): (restconf, "get_interface_state", "name"),
    ("restconf", "plan"): (restconf, "plan_interface", "interface"),
    ("restconf", "apply"): (restconf, "apply_interface", "interface"),
    ("netconf", "status"): (netconf, "get_interface_state", "name"),
    ("netconf", "plan"): (netconf, "plan_interface", "interface"),
    ("netconf", "apply"): (netconf, "apply_interface", "interface"),
    ("ansible", "apply"): (ansible, "apply_interface", "interface"),
    ("netmiko-textfsm", "status"): (netmiko_textfsm, "get_interface_state", "name"),
    ("netmiko-textfsm", "delete"): (netmiko_textfsm, "delete_interface", "name"),
}


def dispatch_request(data):
    route = ROUTES.get((data["method"], data["action"]))
    if route is None:
        return {"status": "error", "result": "invalid_action"}
    module, function_name, kind = route
    interface = data["desired"]["interface"]
    argument = interface["name"] if kind == "name" else interface
    return getattr(module, function_name)(data["router"], argument)
