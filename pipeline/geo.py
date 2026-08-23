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
                   walk starts to sag. Worth a human looking at.
  LEG_FAIL_MIN     12 minutes. Nobody walks that far between two sentences
                   about a wall. This one stops a release.

The split matters. The brief says to flag any leg over about eight minutes, and
flagging is not the same as forbidding: central London genuinely has dull
stretches, and the walk from the Tower up to Leadenhall is one of them. Making
eight minutes fatal would push an author into moving coordinates to please the
tool, which is worse than an honest nine minute leg.

Reversals are the same kind of judgement, so they are a note rather than a
failure. A spur up a river valley has to come back down.

The check does not know what a good route feels like. It knows when one is
obviously wrong, which is the job.
"""
from math import radians, sin, cos, asin, sqrt, atan2, degrees

EARTH_M = 6371008.8
WALK_M_PER_MIN = 80.0
DETOUR = 1.3
LEG_WARN_MIN = 8.0
LEG_FAIL_MIN = 12.0
REVERSAL_DEG = 135.0
MIN_LEG_M = 15.0


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres. Same formula the location gate uses."""
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_M * asin(sqrt(a))


def seg_dist_m(p, a, b):
    """Distance from a point to a line segment, in metres.

    Flat-earth about the point itself, which over the few hundred metres these
    walks cover is right to well under a metre.
    """
    kx = 111320.0 * cos(radians(p[0]))
    ky = 110540.0
    px, py = (p[1] - a[1]) * kx, (p[0] - a[0]) * ky
    bx, by = (b[1] - a[1]) * kx, (b[0] - a[0]) * ky
    l2 = bx * bx + by * by
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / l2))
    dx, dy = px - t * bx, py - t * by
    return sqrt(dx * dx + dy * dy)


def project_on_seg(p, a, b):
    """The point on segment a-b nearest p, as (lat, lon)."""
    kx = 111320.0 * cos(radians(p[0]))
    ky = 110540.0
    px, py = (p[1] - a[1]) * kx, (p[0] - a[0]) * ky
    bx, by = (b[1] - a[1]) * kx, (b[0] - a[0]) * ky
    l2 = bx * bx + by * by
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / l2))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def point_to_line_m(p, line):
    """Distance from a point to the nearest part of a polyline, in metres.

    To the nearest part, not the nearest drawn point. That distinction turned
    out to matter: the first stop of the Noble Val walk stands in the middle of
    a bridge, which OSM draws with a node at each end and nothing between, so
    measuring to nodes put a walker standing on the bridge 41 m off the network.
    """
    if not line:
        return float("inf")
    if len(line) == 1:
        return haversine_m(p[0], p[1], line[0][0], line[0][1])
    return min(seg_dist_m(p, a, b) for a, b in zip(line, line[1:]))


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


def check(points, leg_warn_min=LEG_WARN_MIN, leg_fail_min=LEG_FAIL_MIN):
    """Measure a route and complain about it.

    Returns {legs, total_straight_m, total_walk_m, total_minutes, reversals,
    problems, notes}. `problems` are things that should stop a release.
    `notes` are things a human should look at and may reasonably accept.
    Nothing here raises: the caller decides what to do about either.
    """
    problems, notes = [], []
    if len(points) < 2:
        return {"legs": [], "total_straight_m": 0.0, "total_walk_m": 0.0,
                "total_minutes": 0.0, "reversals": 0,
                "problems": [] if points else ["route has no stops"], "notes": []}

    ls = legs(points)

    seen = set()
    for pid, lat, lon in points:
        if pid in seen:
            problems.append(f"{pid} appears more than once in the order")
        seen.add(pid)
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            problems.append(f"{pid} has an impossible coordinate")

    for leg in ls:
        if leg["minutes"] > leg_fail_min:
            problems.append(
                f"{leg['from']} to {leg['to']} is about {leg['minutes']:.0f} "
                f"minutes ({leg['walk_m']:.0f} m), too far to walk between two stops")
        elif leg["minutes"] > leg_warn_min:
            notes.append(
                f"{leg['from']} to {leg['to']} is about {leg['minutes']:.0f} "
                f"minutes ({leg['walk_m']:.0f} m), over the {leg_warn_min:.0f} "
                f"minute mark")
        if leg["straight_m"] < MIN_LEG_M:
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
            notes.append(f"the walk doubles back at {ls[i]['to']} "
                         f"(turns {t:.0f} degrees)")

    total_straight = sum(l["straight_m"] for l in ls)
    return {
        "legs": ls,
        "total_straight_m": round(total_straight, 1),
        "total_walk_m": round(total_straight * DETOUR, 1),
        "total_minutes": round(walk_minutes(total_straight), 1),
        "reversals": reversals,
        "problems": problems,
        "notes": notes,
    }


# Gate tolerance, retuned after walking Saint-Antonin. A phone's reported
# accuracy is roughly a 68% confidence radius, so subtracting the whole of it
# means "open if there is any plausible chance you are inside". That was too
# generous: a 50 m gate became a 50 + accuracy gate, and under the old 150 m cap
# a poor fix opened a 50 m gate from 200 m away, round a corner, on a different
# street. The allowance is now small, and a fix too vague to be evidence of
# anything is refused rather than believed.
ACC_ALLOWANCE_M = 15.0      # the most a phone's own error estimate can buy you
ACC_USELESS_M = 75.0        # past this the fix says nothing about where you are


def gate_passes(distance_m, reported_accuracy_m, radius_m):
    """The location gate rule.

    Refusing a hopeless fix is the important half. Believing one is how a gate
    opens from a street the walker has never set foot on, and that is worse than
    refusing: they have a pass button, and no way to know the check lied.
    """
    acc = max(0.0, float(reported_accuracy_m or 0.0))
    if acc > ACC_USELESS_M:
        return False
    return (float(distance_m) - min(acc, ACC_ALLOWANCE_M)) <= float(radius_m)
