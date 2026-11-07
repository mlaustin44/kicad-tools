"""Compare native connectivity without treating ratsnest endpoint changes as faults."""
from collections import Counter


def component_index(snapshot, net):
    return {uid: i for i, component in enumerate(snapshot["nets"].get(net, [])) for uid in component}


def preserves_connections(before, after, net):
    """Every old component must survive inside one final component.

    Merging components is allowed. Splits are rejected even if an unrelated
    repair leaves the total disconnected-component count unchanged.
    """
    old = component_index(before, net)
    current = component_index(after, net)
    if not old or not old.keys() <= current.keys():
        return False
    if any(after["item_nets"].get(uid) != net for uid in old):
        return False
    return all(len({current[uid] for uid in component}) == 1
               for component in before["nets"].get(net, []))


def unchanged_unconnected_issues(new, baseline_report, before, after):
    """Identify new-looking ratsnest edges for existing, unimpaired disconnections.

    Both endpoints must be original non-zone items on a net that already had an
    unconnected report. Native components must prove they were disconnected
    before and after, with no loss of any old connection anywhere on that net.
    Unknown objects, zone-only endpoints and new splits remain blocking.
    """
    baseline_nets = set()
    for issue in baseline_report.get("unconnected_items", []):
        if issue.get("severity") == "exclusion":
            continue
        for item in issue.get("items", []):
            net = before["item_nets"].get(item.get("uuid"))
            if net is not None:
                baseline_nets.add(net)
    unchanged = Counter()
    cache = {}
    for identity, count in new.items():
        section, kind, _, items = identity
        if section != "unconnected_items" or kind != "unconnected_items" or len(items) != 2:
            continue
        a, b = (item[0] for item in items)
        net = before["item_nets"].get(a)
        if net is None or net != before["item_nets"].get(b) or net not in baseline_nets:
            continue
        if net not in cache:
            cache[net] = (preserves_connections(before, after, net),
                          component_index(before, net), component_index(after, net))
        preserved, old, current = cache[net]
        if preserved and old[a] != old[b] and current[a] != current[b]:
            unchanged[identity] = count
    return unchanged
