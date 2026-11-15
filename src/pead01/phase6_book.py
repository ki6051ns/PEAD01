"""Portfolio replay on a single shared cash and security ledger."""
from collections import defaultdict

import numpy as np


def book(orders, days, config, cost_override=None, market=None, collect=True, contributions=None):
    """Orders are (row, direction, weight). Net same-time orders before allocation."""
    groups = defaultdict(list)
    for row, side, weight in orders:
        if side and weight > 0 and (side > 0 or row.loanable):
            groups[row.start, row.minute, row.code].append((row, side, weight))
    starts = defaultdict(list)
    for (day, minute, code), values in sorted(groups.items()):
        starts[day].append((minute, code, values))
    daily = np.zeros((len(days), 6))
    holdings = []
    active = {}
    nav = 1.
    for day in range(len(days)):
        room = max(0., nav - sum(size * (marks[day-row.start-1] + abs(h))
                                 for row, side, size, marks, h in active.values()))

        def account(code, item, close):
            row, side, size, marks, h = item
            offset = day - row.start
            prev = marks[offset-1] if offset else 1.
            mark = marks[offset]
            daily[day, 0] += size * side * (mark - prev)
            if contributions is not None:
                contributions[day, int(side < 0)] += size * side * (mark - prev) / nav
            if h:
                daily[day, 0] += size * h * market[1 if offset else 0, day]
            if side < 0 and row.frequency == "daily":
                elapsed = (days[day] - days[day-1]).days if offset else 1
                daily[day, 1] += size * prev * .01 * elapsed / 365
            daily[day, 4] += size * (mark + abs(h))
            if collect:
                holdings.append((day, code, side, row.event_id, row.sector, size * mark))
            if close:
                fee = (row.cost if cost_override is None else cost_override) / 20000
                daily[day, 1] += fee * size * (mark + abs(h))
                daily[day, 2] += size * (mark + abs(h))
                del active[code]
                return size * (mark + abs(h))
            return 0.

        for minute, code, values in starts.get(day, ()):
            for old in list(active):
                item = active[old]
                if item[0].closed and item[0].end == day and item[0].exit_minute < minute:
                    room = min(nav, room + account(old, item, True))
            demand = sum(side * weight for _, side, weight in values)
            side = int(np.sign(demand))
            if code in active or not side:
                continue
            row = max((x for x in values if x[1] == side), key=lambda x: x[2])[0]
            h = -side * row.beta if row.hedge else 0.
            size = min(room/(1+abs(h)), row.capacity, abs(demand)*config["position_limit"]/config["capital"],
                       config["position_limit"]/config["capital"])
            if size <= 0:
                continue
            room -= size * (1 + abs(h))
            active[code] = row, side, size, row.marks, h
            fee = (row.cost if cost_override is None else cost_override) / 20000
            daily[day, 1] += size * (1 + abs(h)) * fee
            daily[day, 2] += size * (1 + abs(h))
            daily[day, 3] += 1
        for code, item in list(active.items()):
            account(code, item, item[0].end == day and item[0].closed)
        daily[day, [0, 1, 2, 4]] /= nav
        daily[day, 5] = daily[day, 0] - daily[day, 1]
        nav *= 1 + daily[day, 5]
        if nav <= 0:
            raise ValueError("NAV exhausted")
    return daily, holdings
