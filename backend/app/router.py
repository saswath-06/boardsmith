from __future__ import annotations

from collections import deque


Point = tuple[int, int]


def _neighbors(point: Point) -> list[Point]:
    x, y = point
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def lee_route(
    start: Point,
    goal: Point,
    blocked: set[Point],
    width: int,
    height: int,
    max_steps: int = 4000,
) -> list[Point] | None:
    """Route a single net on a coarse grid with Lee/BFS.

    Returns None when the search budget is exhausted or no path exists.
    """
    if start == goal:
        return [start]
    queue: deque[Point] = deque([start])
    parent: dict[Point, Point | None] = {start: None}
    steps = 0
    while queue and steps < max_steps:
        steps += 1
        current = queue.popleft()
        for nxt in _neighbors(current):
            x, y = nxt
            if x < 0 or y < 0 or x >= width or y >= height:
                continue
            if nxt in parent:
                continue
            if nxt in blocked and nxt != goal:
                continue
            parent[nxt] = current
            if nxt == goal:
                path = [goal]
                while path[-1] != start:
                    prev = parent[path[-1]]
                    if prev is None:
                        break
                    path.append(prev)
                path.reverse()
                return path
            queue.append(nxt)
    return None
