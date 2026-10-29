from app.planner import build_plan


def plan_interface(
    router,
    desired_interface,
    get_interface_state,
):
    """Build a Part 2 plan from backend status."""
    status = get_interface_state(router, desired_interface["name"])
    if status.get("status") != "ok":
        return status
    current = status["interface"] if status["result"] == "found" else None
    return build_plan(desired_interface, current)
