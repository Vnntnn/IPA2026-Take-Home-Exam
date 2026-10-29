import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from app.backends.common import check_name, classify, error, netmask

ANSIBLE_DIR = Path(__file__).resolve().parents[2] / "ansible"
AUTH_HINTS = ("authentication failed", "invalid/incorrect", "permission denied")


def _playbook_binary():
    local = Path(sys.executable).with_name("ansible-playbook")
    return str(local) if local.exists() else shutil.which("ansible-playbook") or "ansible-playbook"


def _run_playbook(variables):
    # {% raw %} stops Jinja from evaluating '{{ ... }}' typed into a description.
    extra = {}
    for key, value in variables.items():
        if isinstance(value, str):
            if "endraw" in value.lower():
                raise ValueError("unsafe value")
            value = "{% raw %}" + value + "{% endraw %}"
        extra[key] = value

    try:
        result = subprocess.run(
            [
                _playbook_binary(),
                "-i", str(ANSIBLE_DIR / "inventory.ini"),
                str(ANSIBLE_DIR / "apply_interface.yml"),
                "--extra-vars", json.dumps(extra),
            ],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "ANSIBLE_HOST_KEY_CHECKING": "False", "ANSIBLE_NOCOLOR": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectionError("ansible-playbook timed out") from exc

    if result.returncode == 0:
        return
    text = (result.stdout + result.stderr).lower()
    if any(hint in text for hint in AUTH_HINTS):
        raise PermissionError("router rejected credentials")
    if result.returncode == 4 or "unable to connect" in text:
        raise ConnectionError("router unreachable")
    raise RuntimeError(text[-500:])


def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    run_playbook = run_playbook or _run_playbook
    try:
        description = desired_interface["description"]
        if re.search(r"[\r\n]", description):
            raise ValueError("description must be one line")
        run_playbook({
            "router": router,
            "interface_name": check_name(desired_interface["name"]),
            "description": description,
            "ipv4_address": desired_interface["ipv4"].split("/")[0],
            "netmask": netmask(desired_interface["ipv4"]),
            "shutdown": desired_interface["admin_state"] == "down",
        })
        return {"status": "ok", "result": "applied"}
    except Exception as exc:
        return error(classify(exc))
