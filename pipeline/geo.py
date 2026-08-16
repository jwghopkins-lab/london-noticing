#!/usr/bin/env python3
"""Distance, walking time and route sanity checks.

Written from scratch. TRIVIUM had no geographic dimension at all — its stop
order fell out of grid placement — so there was nothing to extend.

The numbers this file is opinionated about:

  WALK_M_PER_MIN   80 m/min, about 4.8 km/h. An unhurried adult who is looking
                   at things, not commuting.
  DETOUR           1.3. Straight-line distance times this approximates the
                   distance actually walked on a street grid. London is not a
                   grid, but 1.3 is close enough to catch a bad leg and it
                   never flatters one.
  LEG_WARN_MIN     8 minutes. Longer than this between two insights and the
                   walk stops being a walk.

The check does not know what a good route feels like. It knows when one is
obviously wrong, which is the job.
"""
from math import radians, sin, cos, asin, sqrt, atan2, degrees

EARTH_M = 6371008.8
WALK_M_PER_MIN = 80.0
DETOUR = 1.3
LEG_WARN_MIN = 8.0
LEG_WARN_M = LEG_WARN_MIN * WALK_M_PER_MIN / DETOUR   # ~492 m straight line
REVERSAL_DEG = 135.0


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres. Same formula the location gate uses."""
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_M * asin(sqrt(a))


def walk_minutes(straight_m):
    """Minutes on foot for a straight-line distance, allowing for streets."""
    return straight_m * DETOUR / WALK_M_PER_MIN


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial compass bearing from the first point to the second."""
    p1, p2 = radians(lat1), radians(lat2)
    dl = radians(lon2 - lon1)
    y = sin(dl) * cos(p2)
    x = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    return (degrees(atan2(y, x)) + 360.0) % 360.0


def turn_deg(b1, b2):
    """How far the walk turns between two legs, 0 straight on, 180 back."""
    d = abs(b2 - b1) % 360.0
    return 360.0 - d if d > 180.0 else d


def legs(points):
    """Per-leg metrics for an ordered list of (id, lat, lon)."""
    out = []
    for i in range(len(points) - 1):
        (a_id, a_lat, a_lon) = points[i]
        (b_id, b_lat, b_lon) = points[i + 1]
        m = haversine_m(a_lat, a_lon, b_lat, b_lon)
        out.append({
            "from": a_id,
            "to": b_id,
            "straight_m": round(m, 1),
            "walk_m": round(m * DETOUR, 1),
            "minutes": round(walk_minutes(m), 1),
            "bearing": round(bearing_deg(a_lat, a_lon, b_lat, b_lon), 1),
        })
    return out


def check(points, leg_warn_min=LEG_WARN_MIN):
    """Measure a route and complain about it.

    Returns {legs, total_straight_m, total_walk_m, total_minutes, reversals,
    problems}. `problems` is a list of plain-English strings, empty when the
    route is fine. Nothing here raises: the caller decides whether a problem
    is fatal, because a draft route is allowed to be bad and a shipped one is
    not.
    """
    problems = []
    if len(points) < 2:
        return {"legs": [], "total_straight_m": 0.0, "total_walk_m": 0.0,
                "total_minutes": 0.0, "reversals": 0,
                "problems": [] if points else ["route has no stops"]}

    ls = legs(points)

    seen = {}
    for pid, lat, lon in points:
        if pid in seen:
            problems.append(f"{pid} appears more than once in the order")
        seen[pid] = True
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            problems.append(f"{pid} has an impossible coordinate")

    for leg in ls:
        if leg["minutes"] > leg_warn_min:
            problems.append(
                f"{leg['from']} to {leg['to']} is about {leg['minutes']:.0f} "
                f"minutes ({leg['walk_m']:.0f} m), over the {leg_warn_min:.0f} "
                f"minute limit")
        if leg["straight_m"] < 15.0:
            problems.append(
                f"{leg['from']} and {leg['to']} are {leg['straight_m']:.0f} m "
                f"apart, which is the same place")

    reversals = 0
    for i in range(len(ls) - 1):
        t = turn_deg(ls[i]["bearing"], ls[i + 1]["bearing"])
        # Only a genuine doubling back counts. An L-shaped turn around a block
        # is how walking works and must not be flagged.
        if t >= REVERSAL_DEG:
            reversals += 1
            problems.append(
                f"the walk doubles back at {ls[i]['to']} "
                f"(turns {t:.0f} degrees)")

    total_straight = sum(l["straight_m"] for l in ls)
    return {
        "legs": ls,
        "total_straight_m": round(total_straight, 1),
        "total_walk_m": round(total_straight * DETOUR, 1),
        "total_minutes": round(walk_minutes(total_straight), 1),
        "reversals": reversals,
        "problems": problems,
    }


def gate_passes(distance_m, reported_accuracy_m, radius_m):
    """The location gate rule, kept exactly as Fedora had it.

    The phone's own accuracy estimate is subtracted from the distance, capped
    at 150 m so a wildly pessimistic reading cannot open a gate from the next
    borough. A gate that can say no to somebody who IS standing there would be
    worse than no gate at all.
    """
    acc = min(float(reported_accuracy_m or 0.0), 150.0)
    return (float(distance_m) - acc) <= float(radius_m)
