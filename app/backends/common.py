"""Helpers shared by every backend: responses, credentials, error mapping."""

import os
import re
from ipaddress import IPv4Interface

import paramiko
import requests
import urllib3
from ncclient.operations import TimeoutExpiredError
from ncclient.transport.errors import (
    AuthenticationError as NcAuthenticationError,
    TransportError as NcTransportError,
)
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TIMEOUT = 8  # seconds; Live allows 20 s per router case


def error(result):
    return {"status": "error", "result": result}


def found(interface):
    return {"status": "ok", "result": "found", "interface": interface}


def not_found():
    return {"status": "ok", "result": "not_found", "interface": None}


def credentials():
    return os.environ.get("ROUTER_USER", ""), os.environ.get("ROUTER_PASS", "")


def classify(exc):
    """Map any transport exception to a backend error code."""
    if isinstance(exc, (
        PermissionError,
        NetmikoAuthenticationException,
        NcAuthenticationError,
        paramiko.AuthenticationException,
    )):
        return "authentication_failed"
    if isinstance(exc, (
        NetmikoTimeoutException,
        NcTransportError,
        TimeoutExpiredError,
        paramiko.SSHException,
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
    )):
        return "connection_failed"
    if isinstance(exc, requests.exceptions.RequestException):
        return "backend_failed"
    if isinstance(exc, OSError):  # ConnectionError, TimeoutError, no route...
        return "connection_failed"
    return "backend_failed"


def cidr(address, mask_or_prefix):
    return str(IPv4Interface(f"{address}/{mask_or_prefix}"))


def netmask(ipv4_cidr):
    return str(IPv4Interface(ipv4_cidr).network.netmask)


def check_name(name):
    """Reject names that could smuggle extra CLI/XML into a command."""
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9/.\-]*", name):
        raise ValueError(f"bad interface name: {name!r}")
    return name


def loopback_number(name):
    match = re.fullmatch(r"Loopback(\d+)", str(name))
    if not match:
        raise ValueError(f"not a Loopback name: {name!r}")
    return int(match.group(1))
