"""Geometry: where a connector leaves a shape, and the number formatter that
the Python renderer and its JavaScript twin must agree on to the last digit.
"""

from __future__ import annotations

import math

import pytest

from figwright.geometry import (
    auto_sides,
    bezier_point,
    boundary_point,
    center,
    edge_geometry,
    fmt,
    polyline_midpoint,
    shape_points,
    side_anchor,
    visual_box,
)


def box(**over):
    node = {"id": "n", "type": "box", "x": 100, "y": 100, "w": 200, "h": 100, "text": ""}
    node.update(over)
    return node


def test_center_and_visual_box():
    assert center(box()) == (200, 150)
    assert visual_box(box()) == (100, 100, 300, 200)


def test_visual_box_covers_a_rotated_shape():
    x0, y0, x1, y1 = visual_box(box(rotation=30))
    assert x0 < 100 and x1 > 300  # the corners swing outside the unrotated box
    assert y0 < 100 and y1 > 200


def test_shape_points_follow_the_shape():
    assert shape_points(box(type="box")) is None  # a rectangle needs no polygon
    diamond = shape_points(box(type="diamond"))
    assert len(diamond) == 4 and (200, 100) in diamond
    assert len(shape_points(box(type="hexagon"))) == 6
    assert len(shape_points(box(type="parallelogram"))) == 4


def test_side_anchor_sits_on_the_named_side():
    node = box()
    assert side_anchor(node, "left", gap=0) == (100, 150)
    assert side_anchor(node, "right", gap=0) == (300, 150)
    assert side_anchor(node, "top", gap=0) == (200, 100)
    assert side_anchor(node, "bottom", gap=0) == (200, 200)
    assert side_anchor(node, "right", gap=5)[0] == 305


def test_boundary_point_leaves_a_circle_on_the_circle():
    circle = box(type="ellipse", x=0, y=0, w=100, h=100)
    p = boundary_point(circle, (500, 50), gap=0)
    assert p[0] == pytest.approx(100) and p[1] == pytest.approx(50)
    p = boundary_point(circle, (50, -500), gap=0)
    assert p[1] == pytest.approx(0)
    diag = boundary_point(circle, (500, -500), gap=0)
    assert math.dist(diag, (50, 50)) == pytest.approx(50, abs=0.5)


def test_auto_sides_prefers_the_dominant_direction():
    assert auto_sides((0, 0), (300, 10)) == ("right", "left")
    assert auto_sides((300, 10), (0, 0)) == ("left", "right")
    assert auto_sides((0, 0), (10, 300)) == ("bottom", "top")
    assert auto_sides((10, 300), (0, 0)) == ("top", "bottom")


def test_bezier_endpoints_and_midpoint():
    p0, c1, c2, p3 = (0, 0), (0, 100), (100, 100), (100, 0)
    assert bezier_point(p0, c1, c2, p3, 0) == p0
    assert bezier_point(p0, c1, c2, p3, 1) == p3
    mid = bezier_point(p0, c1, c2, p3, 0.5)
    assert mid[0] == pytest.approx(50) and mid[1] == pytest.approx(75)


def test_polyline_midpoint_is_half_way_along_the_length():
    assert polyline_midpoint([(0, 0), (10, 0), (10, 10)]) == (10, 0)
    assert polyline_midpoint([(0, 0), (100, 0)]) == (50, 0)
    assert polyline_midpoint([(5, 5)]) == (5, 5)


def test_edge_geometry_connects_two_nodes(tiny_scene):
    edge = tiny_scene["edges"][0]
    g = edge_geometry(tiny_scene, edge)
    assert g and g["path"].startswith("M")
    assert len(g["label"]) == 2  # where the edge label goes
    assert g["heads"] and g["heads"][0]["kind"] == "arrow"
    # The line starts to the right of the first box and ends left of the second.
    assert g["points"][0][0] >= 220 - 1 and g["points"][-1][0] <= 360 + 1


def test_edge_geometry_is_none_when_an_end_is_missing(tiny_scene):
    assert edge_geometry(tiny_scene, {"id": "x", "from": "a", "to": "nope"}) is None


def test_an_end_can_be_a_bare_coordinate():
    scene = {"nodes": [], "edges": [], "style": {}}
    g = edge_geometry(scene, {"id": "e", "from": [0, 0], "to": [100, 0], "routing": "straight"})
    assert g and g["points"][0] == (0.0, 0.0) and g["points"][-1] == (100.0, 0.0)


def test_each_routing_draws_its_own_shape(tiny_scene):
    # Offset the second box so an elbow has a corner to make.
    tiny_scene["nodes"][1]["y"] = 200
    paths = {}
    for routing in ("straight", "curve", "elbow"):
        edge = dict(tiny_scene["edges"][0], routing=routing)
        paths[routing] = edge_geometry(tiny_scene, edge)["path"]
    assert len(set(paths.values())) == 3
    assert "C" in paths["curve"] and paths["elbow"].count("L") >= 2


@pytest.mark.parametrize(
    "value,expected",
    [(1, "1"), (1.0, "1"), (1.04, "1"), (1.05, "1.1"), (-0.0, "0"), (0.04, "0"), (-1.25, "-1.2"),
     (1.25, "1.2"), (1.75, "1.8"), (2.25, "2.2"), (100.0, "100"), (-3.46, "-3.5")],
)
def test_fmt_rounds_like_python(value, expected):
    assert fmt(value) == expected


def test_fmt_never_writes_minus_zero():
    assert fmt(-0.001) == "0"
