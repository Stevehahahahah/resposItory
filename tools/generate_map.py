#!/usr/bin/env python3
"""Generate a Teardown map of Clark University (Worcester, MA).

Looking from Main Street at the campus:

    +------------------------------+      +----------------------+
    |      Jonas Clark Hall        |      | Higgins Univ. Center |
    +-------------+----------------+      +----------+-----------+
          Red Square / Freud                     plaza
    ~~~~~~~~~~~~~~~~~~~~~~ the Green (trees) ~~~~~~~~~~~~~~~~~~~~~~~
    ======== iron fence ======= [ "C" gate ] ========= [ gate ] =====
    ------------------------------ Main Street ----------------------

Both buildings have furnished interiors (classrooms, offices, the
President's office, the dining hall, the Bistro, Tilton Hall, ...).

The whole scene is built in one voxel grid (1 voxel = 0.1 m, Teardown scale)
and exported as equally sized 128^3 MagicaVoxel chunks plus a main.xml.
Grid axes: x = east, y = north (away from Main Street), z = up.
Teardown axes: (x, z, -y).

Usage:  python3 tools/generate_map.py [output_dir]
"""

import math
import os
import shutil
import struct
import sys

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------
# Palette.  In Teardown the palette *index* decides the material:
#   1-8 glass | 9-24 grass | 25-40 dirt | 41-56 rock | 57-72 wood
#   73-88 concrete | 89-104 brick | 105-120 plaster | 121-136 metal
#   137-152 hard metal | 153-168 plastic | 225-240 foliage
# --------------------------------------------------------------------------
GLASS, GLASS_DARK = 1, 2
GRASS, GRASS2, GRASS3 = 9, 10, 11
DIRT, MULCH = 25, 26
GRANITE, GRANITE_DARK, GRANITE_TEXT, SLATE, SLATE2, CHALKBOARD = 41, 42, 43, 44, 45, 46
(TRUNK, DOOR_WOOD, BENCH_WOOD, FLOOR_WOOD, BOOK_RED, BOOK_BLUE, BOOK_GREEN,
 BOOK_TAN, TRUNK2) = 57, 58, 59, 60, 61, 62, 63, 64, 65
(CONCRETE, CONCRETE2, CONCRETE_LIGHT, ASPHALT, ASPHALT2, PAINT_YELLOW,
 PAINT_WHITE, TILE) = 73, 74, 75, 76, 77, 78, 79, 80
BRICK, BRICK2, BRICK3, UC_BRICK, UC_BRICK2, PAVER, PAVER2 = 89, 90, 91, 92, 93, 94, 95
PLASTER, TRIM, WALL_CREAM = 105, 106, 107
(METAL_DARK, METAL_GRAY, ROOF_METAL, ROOF_METAL2, HYDRANT_RED, MAILBOX_BLUE,
 STEEL) = 121, 122, 123, 124, 125, 126, 127
BRONZE, BRONZE_DARK, BRONZE_LIGHT = 137, 138, 139
(LAMP, BLACK_PLASTIC, RUG_RED, RUG_BLUE, SOFA_GREEN, SOFA_BROWN, CHAIR_RED,
 CHAIR_BLUE, POT, CARPET, CARPET2, WHITEBOARD) = range(153, 165)
(LEAF, LEAF2, LEAF3, CONIFER, CONIFER2, RED_LEAF, RED_LEAF2, LOCUST, SHRUB,
 SHRUB2) = range(225, 235)

PALETTE = {
    GLASS: (120, 150, 170), GLASS_DARK: (70, 90, 110),
    GRASS: (88, 134, 58), GRASS2: (78, 122, 50), GRASS3: (100, 146, 66),
    DIRT: (101, 78, 56), MULCH: (82, 55, 38),
    GRANITE: (182, 178, 170), GRANITE_DARK: (140, 136, 130), GRANITE_TEXT: (70, 68, 66),
    SLATE: (62, 66, 72), SLATE2: (72, 76, 82), CHALKBOARD: (38, 60, 48),
    TRUNK: (88, 66, 48), DOOR_WOOD: (92, 52, 30), BENCH_WOOD: (130, 92, 58),
    FLOOR_WOOD: (150, 112, 74), BOOK_RED: (128, 36, 36), BOOK_BLUE: (36, 56, 110),
    BOOK_GREEN: (36, 90, 56), BOOK_TAN: (184, 154, 104), TRUNK2: (70, 54, 42),
    CONCRETE: (176, 172, 164), CONCRETE2: (160, 156, 150), CONCRETE_LIGHT: (204, 200, 190),
    ASPHALT: (58, 58, 60), ASPHALT2: (66, 66, 68), PAINT_YELLOW: (220, 180, 40),
    PAINT_WHITE: (230, 230, 225), TILE: (196, 190, 178),
    BRICK: (148, 62, 44), BRICK2: (132, 54, 40), BRICK3: (160, 74, 52),
    UC_BRICK: (138, 66, 48), UC_BRICK2: (120, 58, 44),
    PAVER: (150, 58, 46), PAVER2: (124, 48, 40),
    PLASTER: (226, 222, 210), TRIM: (236, 232, 220), WALL_CREAM: (232, 222, 196),
    METAL_DARK: (40, 42, 44), METAL_GRAY: (110, 114, 118), ROOF_METAL: (70, 84, 82),
    ROOF_METAL2: (78, 92, 90), HYDRANT_RED: (180, 30, 30), MAILBOX_BLUE: (30, 60, 140),
    STEEL: (170, 175, 180),
    BRONZE: (92, 70, 42), BRONZE_DARK: (62, 46, 30), BRONZE_LIGHT: (190, 150, 70),
    LAMP: (245, 240, 220), BLACK_PLASTIC: (24, 24, 26), RUG_RED: (130, 30, 38),
    RUG_BLUE: (42, 54, 102), SOFA_GREEN: (56, 86, 66), SOFA_BROWN: (96, 58, 38),
    CHAIR_RED: (190, 46, 40), CHAIR_BLUE: (50, 100, 160), POT: (168, 92, 60),
    CARPET: (96, 98, 110), CARPET2: (110, 84, 80), WHITEBOARD: (240, 240, 236),
    LEAF: (62, 104, 40), LEAF2: (52, 90, 34), LEAF3: (76, 118, 46),
    CONIFER: (34, 66, 44), CONIFER2: (28, 56, 38), RED_LEAF: (112, 42, 40),
    RED_LEAF2: (92, 34, 34), LOCUST: (112, 150, 62), SHRUB: (46, 84, 42),
    SHRUB2: (56, 96, 48),
}
TREE_SET = [TRUNK, TRUNK2, LEAF, LEAF2, LEAF3, CONIFER, CONIFER2, RED_LEAF,
            RED_LEAF2, LOCUST, SHRUB, SHRUB2, MULCH]

VOX = 0.1          # metres per voxel
CHUNK = 128
NX, NY, NZ = 1408, 1024, 256
G = np.zeros((NX, NY, NZ), dtype=np.uint8)
rng = np.random.default_rng(1887)


# --------------------------------------------------------------------------
# Primitive helpers (all ranges half-open, clipped to the grid)
# --------------------------------------------------------------------------
def _clip(a, b, n):
    return max(0, int(a)), min(n, int(b))


def box(x0, x1, y0, y1, z0, z1, c):
    x0, x1 = _clip(x0, x1, NX)
    y0, y1 = _clip(y0, y1, NY)
    z0, z1 = _clip(z0, z1, NZ)
    if x0 < x1 and y0 < y1 and z0 < z1:
        G[x0:x1, y0:y1, z0:z1] = c


def box_empty(x0, x1, y0, y1, z0, z1, c):
    """Like box() but only fills empty voxels."""
    x0, x1 = _clip(x0, x1, NX)
    y0, y1 = _clip(y0, y1, NY)
    z0, z1 = _clip(z0, z1, NZ)
    if x0 < x1 and y0 < y1 and z0 < z1:
        sub = G[x0:x1, y0:y1, z0:z1]
        sub[sub == 0] = c


def recolor(x0, x1, y0, y1, z0, z1, old, new):
    x0, x1 = _clip(x0, x1, NX)
    y0, y1 = _clip(y0, y1, NY)
    z0, z1 = _clip(z0, z1, NZ)
    if x0 < x1 and y0 < y1 and z0 < z1:
        sub = G[x0:x1, y0:y1, z0:z1]
        sub[sub == old] = new


def shell(x0, x1, y0, y1, z0, z1, c, t=3):
    """Four walls of thickness t (no floor / roof)."""
    box(x0, x1, y0, y0 + t, z0, z1, c)
    box(x0, x1, y1 - t, y1, z0, z1, c)
    box(x0, x0 + t, y0, y1, z0, z1, c)
    box(x1 - t, x1, y0, y1, z0, z1, c)


def opening(axis, a0, a1, z0, z1, d0, d1, glass_d=None, arch=False, glass=GLASS):
    """Cut a window/door through a wall.

    axis='x': wall runs along x, a = x range, d = y range (wall depth).
    axis='y': wall runs along y, a = y range, d = x range.
    With arch=True a semicircle of diameter (a1-a0) sits on top of z1.
    The opening gets a one-voxel glass pane at depth glass_d (if given).
    """
    r = (a1 - a0) / 2.0
    ac = (a0 + a1) / 2.0
    ztop = z1 + (int(math.ceil(r)) if arch else 0)
    for a in range(int(a0), int(a1)):
        for z in range(int(z0), int(ztop)):
            if z >= z1:
                if (a + 0.5 - ac) ** 2 + (z + 0.5 - z1) ** 2 > r * r:
                    continue
            if axis == 'x':
                box(a, a + 1, d0, d1, z, z + 1, 0)
                if glass_d is not None:
                    box(a, a + 1, glass_d, glass_d + 1, z, z + 1, glass)
            else:
                box(d0, d1, a, a + 1, z, z + 1, 0)
                if glass_d is not None:
                    box(glass_d, glass_d + 1, a, a + 1, z, z + 1, glass)


def arch_ring(axis, a0, a1, z1, d0, d1, c, thick=2):
    """Brick/stone voussoir ring around an arched opening."""
    r = (a1 - a0) / 2.0
    ac = (a0 + a1) / 2.0
    for a in range(int(a0 - thick), int(a1 + thick)):
        for z in range(int(z1), int(z1 + r + thick + 1)):
            dist = math.hypot(a + 0.5 - ac, z + 0.5 - z1)
            if r <= dist < r + thick:
                if axis == 'x':
                    box(a, a + 1, d0, d1, z, z + 1, c)
                else:
                    box(d0, d1, a, a + 1, z, z + 1, c)


def sphere_mask(cx, cy, cz, rx, ry, rz):
    x0, x1 = _clip(cx - rx - 1, cx + rx + 2, NX)
    y0, y1 = _clip(cy - ry - 1, cy + ry + 2, NY)
    z0, z1 = _clip(cz - rz - 1, cz + rz + 2, NZ)
    xs = (np.arange(x0, x1) + 0.5 - cx)[:, None, None] / rx
    ys = (np.arange(y0, y1) + 0.5 - cy)[None, :, None] / ry
    zs = (np.arange(z0, z1) + 0.5 - cz)[None, None, :] / rz
    return (slice(x0, x1), slice(y0, y1), slice(z0, z1)), (xs ** 2 + ys ** 2 + zs ** 2) <= 1.0


def ball(cx, cy, cz, r, c):
    sl, m = sphere_mask(cx, cy, cz, r, r, r)
    G[sl][m] = c


def disc(cx, cy, r, z0, z1, c):
    x0, x1 = _clip(cx - r - 1, cx + r + 2, NX)
    y0, y1 = _clip(cy - r - 1, cy + r + 2, NY)
    xs = (np.arange(x0, x1) + 0.5 - cx)[:, None]
    ys = (np.arange(y0, y1) + 0.5 - cy)[None, :]
    m = xs ** 2 + ys ** 2 <= r * r
    for z in range(max(0, z0), min(NZ, z1)):
        G[x0:x1, y0:y1, z][m] = c


def c_letter(cx, cy, z, r_in, r_out, c, plane='xy', y_plane=None):
    """A ring open towards +x: the letter C (flat on the floor or in a wall)."""
    for a in range(int(cx - r_out) - 1, int(cx + r_out) + 2):
        for b in range(int(cy - r_out) - 1, int(cy + r_out) + 2):
            da, db = a + 0.5 - cx, b + 0.5 - cy
            d = math.hypot(da, db)
            if r_in <= d < r_out and abs(math.atan2(db, da)) > 0.75:
                if plane == 'xy':
                    box(a, a + 1, b, b + 1, z, z + 1, c)
                else:                       # (a, b) = (x, z) in the wall plane y_plane
                    box(a, a + 1, y_plane[0], y_plane[1], b, b + 1, c)


def thick_line(xa, ya, xb, yb, w, z, c):
    """Straight path of width w on layer z."""
    x0, x1 = _clip(min(xa, xb) - w, max(xa, xb) + w, NX)
    y0, y1 = _clip(min(ya, yb) - w, max(ya, yb) + w, NY)
    px = np.arange(x0, x1)[:, None] + 0.5
    py = np.arange(y0, y1)[None, :] + 0.5
    dx, dy = xb - xa, yb - ya
    L2 = dx * dx + dy * dy
    t = np.clip(((px - xa) * dx + (py - ya) * dy) / L2, 0, 1)
    d = np.hypot(px - (xa + t * dx), py - (ya + t * dy))
    G[x0:x1, y0:y1, z][d <= w / 2.0] = c


def capsule(p0, p1, r0, r1, c):
    """Tapered cylinder with round ends (tree trunks and limbs), empty voxels only."""
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    rm = max(r0, r1) + 1
    lo = np.maximum(np.floor(np.minimum(p0, p1) - rm).astype(int), 0)
    hi = np.minimum(np.ceil(np.maximum(p0, p1) + rm).astype(int) + 1, [NX, NY, NZ])
    if np.any(hi <= lo):
        return
    X = np.arange(lo[0], hi[0])[:, None, None] + 0.5
    Y = np.arange(lo[1], hi[1])[None, :, None] + 0.5
    Z = np.arange(lo[2], hi[2])[None, None, :] + 0.5
    ab = p1 - p0
    L2 = max(float(ab @ ab), 1e-9)
    t = np.clip(((X - p0[0]) * ab[0] + (Y - p0[1]) * ab[1] + (Z - p0[2]) * ab[2]) / L2, 0, 1)
    r = r0 + (r1 - r0) * t
    d2 = ((X - p0[0] - t * ab[0]) ** 2 + (Y - p0[1] - t * ab[1]) ** 2
          + (Z - p0[2] - t * ab[2]) ** 2)
    sub = G[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]]
    m = (d2 <= r * r) & (sub == 0)
    sub[m] = c


def pavers(x0, x1, y0, y1, z=0):
    """Red brick pavers in a basket-weave pattern."""
    x0, x1 = _clip(x0, x1, NX)
    y0, y1 = _clip(y0, y1, NY)
    ys = np.arange(y0, y1)
    for x in range(x0, x1):
        pat = ((x // 4) + (ys // 2) + (x // 8)) % 3
        G[x, y0:y1, z] = np.where(pat == 0, PAVER2, PAVER)


# --------------------------------------------------------------------------
# 5x7 voxel font
# --------------------------------------------------------------------------
FONT = {
    'A': [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    'C': [" ####", "#    ", "#    ", "#    ", "#    ", "#    ", " ####"],
    'E': ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    'G': [" ####", "#    ", "#    ", "#  ##", "#   #", "#   #", " ### "],
    'H': ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    'I': ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    'K': ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    'L': ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    'N': ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    'O': [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    'R': ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    'S': [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    'T': ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    'U': ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    'V': ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    'Y': ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    '1': ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    '7': ["#####", "    #", "   # ", "  #  ", "  #  ", "  #  ", "  #  "],
    '8': [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    ' ': ["     "] * 7,
}


def text_width(s):
    return len(s) * 6 - 1


def draw_text(s, x_center, z_top, y_face, c, reading_dir=1):
    """Write text on a wall facing -y (reading_dir=+1) or +y (reading_dir=-1)."""
    w = text_width(s)
    start = x_center - reading_dir * (w // 2)
    for i, ch in enumerate(s):
        for row, line in enumerate(FONT[ch]):
            for col, px in enumerate(line):
                if px == '#':
                    x = start + reading_dir * (i * 6 + col)
                    box(x, x + 1, y_face, y_face + 1, z_top - row, z_top - row + 1, c)


# --------------------------------------------------------------------------
# Building interiors: slabs, walls, stairs, lights
# --------------------------------------------------------------------------
def floor_slab(x0, x1, y0, y1, z, wood=True):
    box(x0, x1, y0, y1, z - 2, z, CONCRETE)
    if wood:
        box(x0, x1, y0, y1, z - 1, z, FLOOR_WOOD)


def interior_wall_x(x0, x1, y, z0, z1, doors, door_w=12, door_h=24, col=PLASTER):
    """Wall along x at y..y+2 with framed door openings centred at `doors`."""
    box(x0, x1, y, y + 2, z0, z1, col)
    for dx in doors:
        box(dx - door_w // 2 - 1, dx + door_w // 2 + 1, y, y + 2, z0, z0 + door_h + 1, DOOR_WOOD)
        box(dx - door_w // 2, dx + door_w // 2, y, y + 2, z0, z0 + door_h, 0)


def railing_x(x0, x1, y, z):
    box_empty(x0, x1, y, y + 1, z + 9, z + 10, METAL_DARK)
    for x in range(x0, x1, 6):
        box_empty(x, x + 1, y, y + 1, z, z + 9, METAL_DARK)


def railing_y(x, y0, y1, z):
    box_empty(x, x + 1, y0, y1, z + 9, z + 10, METAL_DARK)
    for y in range(y0, y1, 6):
        box_empty(x, x + 1, y, y + 1, z, z + 9, METAL_DARK)


def stairs(x_bottom, lane, z_base, z_top, direction=1, rails=('-y', '+y'), run=3):
    """Solid stair along x in `lane` (y range); climbs towards +x (direction=1)
    or -x.  Cuts the hole in the slab above and puts railings round it,
    leaving the arrival end open."""
    y0, y1 = lane
    rise = z_top - z_base
    steps = int(math.ceil(rise / 2.0))
    for i in range(steps):
        top = z_base + int(round((i + 1) * rise / steps))
        xa = x_bottom + i * run if direction > 0 else x_bottom - (i + 1) * run
        box(xa, xa + run, y0, y1, z_base, top, CONCRETE2)
    x_top = x_bottom + direction * steps * run
    hx0, hx1 = min(x_bottom, x_top) - 4, max(x_bottom, x_top) + 4
    box(hx0, hx1, y0 - 1, y1 + 1, z_top - 2, z_top, 0)
    if '-y' in rails:
        railing_x(hx0, hx1, y0 - 2, z_top)
    if '+y' in rails:
        railing_x(hx0, hx1, y1 + 1, z_top)
    railing_y(hx0 - 1 if direction > 0 else hx1, y0 - 2, y1 + 2, z_top)


def ceiling_lights(x0, x1, y0, y1, z_ceiling, n=2):
    cy = (y0 + y1) // 2
    for i in range(n):
        cx = x0 + (x1 - x0) * (2 * i + 1) // (2 * n)
        box(cx - 4, cx + 4, cy - 2, cy + 2, z_ceiling - 1, z_ceiling, LAMP)


def radiator(axis, a0, a1, d0, d1, z):
    if axis == 'x':
        box(a0, a1, d0, d1, z + 1, z + 6, METAL_GRAY)
    else:
        box(d0, d1, a0, a1, z + 1, z + 6, METAL_GRAY)


# --------------------------------------------------------------------------
# Furniture.  A piece is a list of local boxes (x0, x1, y0, y1, z0, z1, c)
# starting at 0; its "front" is the -y side (where a sitter's knees point,
# where a shelf is open, the side of a board you write on, ...).
# --------------------------------------------------------------------------
FACING = {'-y': 0, '+x': 1, '+y': 2, '-x': 3}


def extent(parts):
    return max(p[1] for p in parts), max(p[3] for p in parts)


def shift(parts, dx=0, dy=0, dz=0):
    return [(a + dx, b + dx, c + dy, d + dy, e + dz, f + dz, col)
            for a, b, c, d, e, f, col in parts]


def rotate(parts, k):
    """Rotate so the front faces -y, +x, +y, -x for k = 0, 1, 2, 3."""
    W, D = extent(parts)
    out = []
    for x0, x1, y0, y1, z0, z1, c in parts:
        if k == 0:
            r = (x0, x1, y0, y1)
        elif k == 1:
            r = (D - y1, D - y0, x0, x1)
        elif k == 2:
            r = (W - x1, W - x0, D - y1, D - y0)
        else:
            r = (y0, y1, W - x1, W - x0)
        out.append(r + (z0, z1, c))
    return out


def footprint(parts, facing):
    W, D = extent(parts)
    return (W, D) if FACING[facing] % 2 == 0 else (D, W)


def place(parts, x, y, z, facing='-y'):
    for x0, x1, y0, y1, z0, z1, c in rotate(parts, FACING[facing]):
        box(x + x0, x + x1, y + y0, y + y1, z + z0, z + z1, c)


class Room:
    """A room with its window wall on one y side and the door wall on the
    other.  put() takes (u, v) with u along x from x0 and v measured from the
    window wall towards the door wall; facings are given in that frame."""

    def __init__(self, x0, x1, y0, y1, z, door='+y'):
        self.x0, self.x1, self.y0, self.y1, self.z, self.door = x0, x1, y0, y1, z, door
        self.w, self.d = x1 - x0, y1 - y0

    def put(self, parts, u, v, facing='-y', dz=0):
        W, D = footprint(parts, facing)
        if self.door == '+y':
            place(parts, self.x0 + u, self.y0 + v, self.z + dz, facing)
        else:
            f = {'+y': '-y', '-y': '+y'}.get(facing, facing)
            place(parts, self.x0 + u, self.y1 - v - D, self.z + dz, f)


def chair(seat=BENCH_WOOD, leg=DOOR_WOOD):
    p = [(x, x + 1, y, y + 1, 0, 4, leg) for x in (0, 4) for y in (0, 4)]
    return p + [(0, 5, 0, 5, 4, 5, seat), (0, 5, 4, 5, 5, 10, seat)]


def office_chair(col=BLACK_PLASTIC):
    return [(2, 3, 2, 3, 1, 4, METAL_DARK), (0, 5, 2, 3, 0, 1, METAL_DARK),
            (2, 3, 0, 5, 0, 1, METAL_DARK), (0, 5, 0, 5, 4, 5, col), (0, 5, 4, 5, 5, 11, col)]


def stool(col=BLACK_PLASTIC, h=6):
    return [(1, 2, 1, 2, 0, h, METAL_DARK), (0, 3, 0, 3, 0, 1, METAL_DARK), (0, 3, 0, 3, h, h + 1, col)]


def table(w, d, top=BENCH_WOOD, leg=DOOR_WOOD, h=7):
    p = [(0, w, 0, d, h, h + 1, top)]
    return p + [(x, x + 1, y, y + 1, 0, h, leg) for x in (0, w - 1) for y in (0, d - 1)]


def student_desk():
    return table(10, 6, BENCH_WOOD, METAL_DARK) + shift(chair(BENCH_WOOD, METAL_DARK), 2, 6)


def teacher_desk():
    p = [(0, 14, 0, 7, 7, 8, DOOR_WOOD), (0, 4, 0, 7, 0, 7, DOOR_WOOD),
         (10, 14, 0, 7, 0, 7, DOOR_WOOD), (4, 10, 0, 1, 1, 7, DOOR_WOOD),
         (2, 6, 2, 5, 8, 9, BOOK_RED), (9, 12, 2, 4, 8, 9, PLASTER)]
    return p + shift(chair(DOOR_WOOD, DOOR_WOOD), 5, 8)


def office_desk(top=BENCH_WOOD):
    """Desk with a computer; the user sits on the +y side facing -y."""
    p = [(0, 14, 0, 7, 7, 8, top), (0, 4, 0, 7, 0, 7, DOOR_WOOD), (13, 14, 0, 7, 0, 7, DOOR_WOOD),
         (5, 9, 1, 2, 9, 13, BLACK_PLASTIC), (6, 8, 1, 3, 8, 9, BLACK_PLASTIC),
         (5, 9, 3, 5, 8, 9, METAL_GRAY), (10, 12, 2, 5, 8, 9, PLASTER)]
    return p + shift(office_chair(), 5, 8)


def exec_desk():
    p = [(0, 24, 0, 9, 7, 8, DOOR_WOOD), (0, 6, 0, 9, 0, 7, DOOR_WOOD),
         (18, 24, 0, 9, 0, 7, DOOR_WOOD), (6, 18, 0, 1, 1, 7, DOOR_WOOD),
         (2, 3, 2, 3, 8, 12, BRONZE_LIGHT), (1, 4, 1, 4, 12, 14, LAMP),
         (9, 15, 3, 7, 8, 9, PLASTER), (19, 22, 2, 5, 8, 10, BOOK_RED)]
    return p + [(11, 13, 12, 14, 0, 4, METAL_DARK), (9, 15, 10, 16, 4, 6, SOFA_BROWN),
                (9, 15, 15, 17, 6, 14, SOFA_BROWN)]


def bookshelf(w=10, h=20, seed=0, frame=DOOR_WOOD, items=(BOOK_RED, BOOK_BLUE, BOOK_GREEN, BOOK_TAN)):
    r = np.random.default_rng(seed)
    p = [(0, 1, 0, 3, 0, h, frame), (w - 1, w, 0, 3, 0, h, frame),
         (0, w, 2, 3, 0, h, frame), (0, w, 0, 3, h - 1, h, frame)]
    for s in range(0, h - 3, 5):
        p.append((0, w, 0, 3, s, s + 1, frame))
        room = min(s + 5, h - 1) - (s + 1)
        for x in range(1, w - 1):
            if r.random() < 0.85:
                bh = int(r.integers(max(2, room - 1), room + 1))
                p.append((x, x + 1, 0, 2, s + 1, s + 1 + bh, int(r.choice(items))))
    return p


def board(w=40, col=CHALKBOARD, frame=DOOR_WOOD, marks=(PLASTER,), seed=0):
    """Chalk/white board; mounted on a wall with its front (-y) to the room."""
    r = np.random.default_rng(seed)
    p = [(0, w, 1, 2, 9, 27, col), (0, w, 1, 2, 8, 9, frame), (0, w, 1, 2, 27, 28, frame),
         (0, 1, 1, 2, 8, 28, frame), (w - 1, w, 1, 2, 8, 28, frame), (1, w - 1, 0, 1, 9, 10, frame)]
    for line in range(4):
        z = 24 - line * 4
        x = 3
        while x < w - 6:
            L = int(r.integers(2, 7))
            if r.random() < 0.75:
                p.append((x, min(x + L, w - 3), 1, 2, z, z + 1, int(r.choice(marks))))
            x += L + 1
    return p


def whiteboard(w=30, seed=0):
    return board(w, WHITEBOARD, METAL_GRAY, (CHAIR_BLUE, CHAIR_RED, BLACK_PLASTIC), seed)


def painting(w=12, h=14, kind='portrait'):
    p = [(0, w, 0, 1, 0, h, DOOR_WOOD)]
    if kind == 'portrait':
        p += [(1, w - 1, 0, 1, 1, h - 1, TRUNK2), (w // 2 - 2, w // 2 + 2, 0, 1, h - 7, h - 3, BOOK_TAN),
              (w // 2 - 3, w // 2 + 3, 0, 1, 1, h - 7, BLACK_PLASTIC)]
    else:
        p += [(1, w - 1, 0, 1, h // 2, h - 1, CHAIR_BLUE), (1, w - 1, 0, 1, 1, h // 2, LEAF3),
              (w // 3, w // 3 + 3, 0, 1, h // 2 - 2, h // 2 + 3, LEAF2)]
    return p


def bulletin_board(w=16, h=10, seed=0):
    r = np.random.default_rng(seed)
    p = [(0, w, 0, 1, 0, h, BOOK_TAN)]
    for _ in range(6):
        x, z = int(r.integers(1, w - 3)), int(r.integers(1, h - 3))
        p.append((x, x + 2, 0, 1, z, z + 3, int(r.choice([PLASTER, CHAIR_RED, CHAIR_BLUE, WHITEBOARD]))))
    return p


def sofa(w=20, col=SOFA_GREEN):
    p = [(0, w, 0, 8, 1, 4, col), (0, w, 6, 8, 4, 10, col), (0, 2, 0, 8, 4, 7, col),
         (w - 2, w, 0, 8, 4, 7, col)]
    return p + [(x, x + 1, y, y + 1, 0, 1, DOOR_WOOD) for x in (0, w - 1) for y in (0, 7)]


def armchair(col=SOFA_BROWN):
    return sofa(9, col)


def coffee_table():
    return table(10, 6, DOOR_WOOD, DOOR_WOOD, 3)


def rug(w, d, col, border=BOOK_TAN):
    return [(0, w, 0, d, 0, 1, border), (1, w - 1, 1, d - 1, 0, 1, col)]


def plant(h=9):
    return [(1, 4, 1, 4, 0, 4, POT), (1, 4, 1, 4, 4, h, SHRUB), (0, 5, 1, 4, 5, h - 1, SHRUB2),
            (1, 4, 0, 5, 5, h - 1, SHRUB2)]


def filing_cabinet():
    return [(0, 4, 0, 5, 0, 13, METAL_GRAY)] + [(0, 4, 0, 1, z, z + 1, METAL_DARK) for z in (4, 8, 12)]


def display_case(w=16, d=6, item=BRONZE):
    return [(0, w, 0, d, 0, 9, DOOR_WOOD), (0, w, 0, d, 9, 16, GLASS), (1, w - 1, 1, d - 1, 9, 15, 0),
            (3, 6, 2, 4, 9, 11, BOOK_RED), (3, 6, 2, 4, 11, 12, BOOK_TAN),
            (9, 12, 2, 4, 9, 12, item), (10, 11, 2, 4, 12, 14, item)]


def conference_table(w=36, d=12, col=DOOR_WOOD, chair_col=BLACK_PLASTIC):
    p = shift(table(w, d, col, col), 0, 5)
    for x in range(3, w - 5, 9):
        p += shift(rotate(office_chair(chair_col), 2), x, 0)
        p += shift(office_chair(chair_col), x, 5 + d)
    return p


def dining_table(w=36, chair_col=CHAIR_RED):
    p = shift(table(w, 8, BENCH_WOOD, METAL_DARK), 0, 5)
    for x in range(2, w - 4, 9):
        p += shift(rotate(chair(chair_col, METAL_DARK), 2), x, 0)
        p += shift(chair(chair_col, METAL_DARK), x, 13)
    return p


def cafe_set(chair_col=CHAIR_RED):
    return (rotate(chair(chair_col, METAL_DARK), 1) + shift(table(8, 8, BENCH_WOOD, METAL_DARK), 6, 0)
            + shift(rotate(chair(chair_col, METAL_DARK), 3), 15, 0))


def counter(w, d=7, base=DOOR_WOOD, top=GRANITE):
    return [(0, w, 1, d, 0, 10, base), (0, w, 0, d, 10, 11, top)]


def serving_line(w=90):
    p = [(0, w, 1, 9, 0, 9, STEEL), (0, w, 1, 9, 9, 10, STEEL), (0, w, 0, 1, 7, 8, STEEL)]
    foods = (BOOK_TAN, LEAF3, CHAIR_RED, PAINT_YELLOW, BOOK_RED)
    for i, x in enumerate(range(4, w - 6, 9)):
        p.append((x, x + 6, 3, 7, 9, 10, foods[i % len(foods)]))
    for x in range(0, w, 15):
        p.append((x, x + 1, 7, 8, 10, 15, STEEL))
    return p + [(0, w, 3, 8, 15, 16, GLASS)]


def lab_bench(w=30):
    return [(0, w, 0, 8, 0, 8, DOOR_WOOD), (0, w, 0, 8, 8, 9, BLACK_PLASTIC),
            (4, 7, 2, 5, 9, 12, GLASS), (12, 14, 3, 5, 9, 14, STEEL), (12, 16, 3, 4, 14, 15, STEEL),
            (20, 24, 2, 6, 9, 11, BRONZE_LIGHT), (26, 28, 3, 5, 9, 13, GLASS)]


def crate(s=7):
    return [(0, s, 0, s, 0, s, BENCH_WOOD), (0, s, 0, s, s // 2, s // 2 + 1, DOOR_WOOD)]


def grand_piano():
    """Bench on the -y side, keys facing it."""
    return [(4, 11, 0, 3, 0, 5, BLACK_PLASTIC),
            (0, 15, 5, 13, 6, 10, BLACK_PLASTIC), (0, 9, 13, 19, 6, 10, BLACK_PLASTIC),
            (9, 12, 13, 16, 6, 10, BLACK_PLASTIC), (1, 14, 4, 6, 8, 9, WHITEBOARD),
            (5, 10, 7, 8, 10, 14, BLACK_PLASTIC),
            (1, 2, 6, 7, 0, 6, BLACK_PLASTIC), (13, 14, 6, 7, 0, 6, BLACK_PLASTIC),
            (4, 5, 17, 18, 0, 6, BLACK_PLASTIC)]


def podium():
    return [(0, 6, 1, 5, 0, 12, DOOR_WOOD), (0, 6, 0, 3, 12, 13, DOOR_WOOD)]


def stove():
    p = [(0, 8, 0, 7, 0, 9, STEEL), (1, 7, 0, 1, 2, 7, BLACK_PLASTIC)]
    return p + [(x, x + 2, y, y + 2, 9, 10, BLACK_PLASTIC) for x in (1, 5) for y in (2, 5)]


def fridge():
    return [(0, 8, 0, 7, 0, 20, STEEL), (0, 8, 0, 1, 12, 13, METAL_DARK), (6, 7, 0, 1, 4, 11, METAL_DARK)]


def vending(col=CHAIR_RED):
    return [(0, 9, 0, 7, 0, 18, col), (1, 6, 0, 1, 6, 16, GLASS), (7, 8, 0, 1, 8, 12, METAL_DARK)]


def pool_table():
    p = [(0, 25, 0, 14, 0, 7, DOOR_WOOD), (1, 24, 1, 13, 7, 8, SOFA_GREEN),
         (0, 25, 0, 1, 7, 8, DOOR_WOOD), (0, 25, 13, 14, 7, 8, DOOR_WOOD),
         (0, 1, 0, 14, 7, 8, DOOR_WOOD), (24, 25, 0, 14, 7, 8, DOOR_WOOD)]
    for x, y, c in ((6, 7, WHITEBOARD), (16, 5, CHAIR_RED), (17, 8, PAINT_YELLOW), (19, 6, CHAIR_BLUE),
                    (18, 10, BLACK_PLASTIC)):
        p.append((x, x + 1, y, y + 1, 8, 9, c))
    return p


def ping_pong():
    return table(27, 15, CHAIR_BLUE, METAL_DARK) + [(13, 14, 0, 15, 8, 10, WHITEBOARD),
                                                    (0, 27, 7, 8, 7, 8, WHITEBOARD)]


def arcade():
    return [(0, 7, 0, 7, 0, 18, BLACK_PLASTIC), (1, 6, 0, 1, 10, 15, CHAIR_BLUE),
            (1, 6, 0, 2, 8, 9, METAL_GRAY), (1, 6, 0, 1, 16, 17, CHAIR_RED)]


def copier():
    return [(0, 10, 0, 7, 0, 10, STEEL), (0, 10, 0, 7, 10, 11, BLACK_PLASTIC), (2, 8, 1, 6, 11, 12, PLASTER)]


def tv(w=24):
    return [(0, w, 0, 1, 0, 14, BLACK_PLASTIC)]


def mailboxes(w=80, h=24):
    p = [(0, w, 0, 1, 0, h, BRONZE_LIGHT)]
    p += [(x, x + 1, 0, 1, 0, h, BRONZE_DARK) for x in range(0, w, 4)]
    return p + [(0, w, 0, 1, z, z + 1, BRONZE_DARK) for z in range(0, h, 3)]


def bench(length=16):
    """Park bench; the backrest is on the +y side."""
    p = [(x, x + 2, 0, 5, 0, 5, METAL_DARK) for x in (1, length - 3)]
    return p + [(0, length, 0, 5, 5, 6, BENCH_WOOD), (0, length, 4, 5, 6, 10, BENCH_WOOD)]


def trash_can():
    return [(0, 4, 0, 4, 0, 9, METAL_DARK), (1, 3, 1, 3, 8, 9, 0)]


def round_table(cx, cy, z, r=7, n=6, cloth=WHITEBOARD, chair_col=CHAIR_RED):
    disc(cx, cy, r, z + 7, z + 8, cloth)
    box(int(cx) - 1, int(cx) + 1, int(cy) - 1, int(cy) + 1, z, z + 7, METAL_DARK)
    for i in range(n):
        a = 2 * math.pi * i / n
        px, py = cx + (r + 4) * math.cos(a), cy + (r + 4) * math.sin(a)
        if abs(math.cos(a)) > abs(math.sin(a)):
            f = '-x' if math.cos(a) > 0 else '+x'
        else:
            f = '-y' if math.sin(a) > 0 else '+y'
        place(chair(chair_col, METAL_DARK), int(px) - 2, int(py) - 2, z, f)


# --------------------------------------------------------------------------
# Jonas Clark Hall (faces Main Street / -y)
# --------------------------------------------------------------------------
JX0, JX1, JY0, JY1 = 200, 800, 680, 860
JL = [1, 26, 71, 116, 161]                   # basement, 1st, 2nd, 3rd floor, attic floor
J_TOP = JL[4]
BAY_X0, BAY_X1, BAY_Y0 = 445, 555, 672       # projecting central bay
J_ROOMS = dict(A=(203, 293), B=(295, 383), C=(385, 443), H=(445, 555),
               C2=(557, 615), B2=(617, 705), A2=(707, 797))
J_FRONT, J_BACK = (683, 755), (787, 857)     # room depths either side of the corridor
J_CROSS = (293, 383, 443, 555, 615, 705)     # cross walls (2 voxels thick)


def jonas_clark_hall():
    T = 3
    box(JX0, JX1, JY0, JY1, 0, 1, CONCRETE)
    shell(JX0, JX1, JY0, JY1, 1, JL[1], GRANITE, T)          # raised granite basement
    shell(JX0, JX1, JY0, JY1, JL[1], J_TOP, BRICK, T)
    for x0 in (JX0 - 2, JX1 - 10):                          # corner pilasters
        for ya, yb in ((JY0 - 2, JY0 + 4), (JY1 - 4, JY1 + 2)):
            box(x0, x0 + 12, ya, yb, 1, J_TOP, BRICK)
            box(x0, x0 + 12, ya, yb, 1, JL[1], GRANITE)
    box(BAY_X0, BAY_X1, BAY_Y0, JY0 + T, 1, J_TOP, BRICK)    # central bay
    box(BAY_X0, BAY_X1, BAY_Y0, JY0 + T, 1, JL[1], GRANITE)

    for z in (JL[1] - 2, JL[2] - 2, JL[3] - 2):             # granite belt courses
        box(JX0 - 1, JX1 + 1, JY0 - 1, JY0, z, z + 3, GRANITE)
        box(JX0 - 1, JX1 + 1, JY1, JY1 + 1, z, z + 3, GRANITE)
        box(JX0 - 1, JX0, JY0, JY1, z, z + 3, GRANITE)
        box(JX1, JX1 + 1, JY0, JY1, z, z + 3, GRANITE)
        box(BAY_X0 - 1, BAY_X1 + 1, BAY_Y0 - 1, BAY_Y0, z, z + 3, GRANITE)

    # ---- windows (with radiators inside) ---------------------------------
    west = list(range(JX0 + 25, BAY_X0 - 25, 30))           # 225 .. 405
    front_cols = west + [1000 - c for c in west]
    back_cols = front_cols + [470, 500, 530]
    side_rows = list(range(JY0 + 40, JY1 - 25, 45))         # 720, 765, 810
    arch_z = JL[3] + 8

    def floor_windows(axis, centres, d0, d1, gd, out_d, rad):
        for c in centres:
            a0, a1 = c - 7, c + 7
            opening(axis, a0, a1, 8, 20, d0, d1, gd)                       # basement
            for zb in (JL[1] + 8, JL[2] + 8):                              # floors 1-2
                opening(axis, a0, a1, zb, zb + 28, d0, d1, gd)
                if axis == 'x':
                    box(a0 - 2, a1 + 2, out_d, out_d + 1, zb + 28, zb + 31, GRANITE)
                    box(a0 - 1, a1 + 1, out_d, out_d + 1, zb - 2, zb, GRANITE)
                else:
                    box(out_d, out_d + 1, a0 - 2, a1 + 2, zb + 28, zb + 31, GRANITE)
                    box(out_d, out_d + 1, a0 - 1, a1 + 1, zb - 2, zb, GRANITE)
            arch_ring(axis, a0, a1, arch_z + 20, out_d, out_d + 1, BRICK2)  # floor 3 arches
            opening(axis, a0, a1, arch_z, arch_z + 20, d0, d1, gd, arch=True)
            for zf in JL[1:4]:
                radiator(axis, a0 - 1, a1 + 1, rad[0], rad[1], zf)

    floor_windows('x', front_cols, JY0, JY0 + T, JY0 + 1, JY0 - 1, (JY0 + T, JY0 + T + 2))
    floor_windows('x', back_cols, JY1 - T, JY1, JY1 - 2, JY1, (JY1 - T - 2, JY1 - T))
    floor_windows('y', side_rows, JX0, JX0 + T, JX0 + 1, JX0 - 1, (JX0 + T, JX0 + T + 2))
    floor_windows('y', side_rows, JX1 - T, JX1, JX1 - 2, JX1, (JX1 - T - 2, JX1 - T))

    # ---- central bay: steps, entrance, name blocks, arched windows -------
    for i in range(13):
        ys = BAY_Y0 - 4 * (13 - i)
        box(466, 534, ys, BAY_Y0, 1, 2 * (i + 1), GRANITE)
        box(461, 466, ys, ys + 4, 1, 2 * (i + 1) + 6, GRANITE_DARK)       # cheek walls
        box(534, 539, ys, ys + 4, 1, 2 * (i + 1) + 6, GRANITE_DARK)
    dz = JL[1] + 26
    opening('x', 485, 515, JL[1], dz, BAY_Y0, JY0 + T)
    arch_ring('x', 485, 515, dz, BAY_Y0 - 1, BAY_Y0, GRANITE, thick=3)
    opening('x', 485, 515, dz, dz + 1, BAY_Y0, JY0 + T, BAY_Y0 + 4, arch=True)
    box(485, 515, BAY_Y0, JY0 + T, dz, dz + 1, DOOR_WOOD)                 # transom bar
    box(486, 488, JY0 + T, JY0 + T + 14, JL[1], JL[1] + 24, DOOR_WOOD)     # open door leaves
    box(512, 514, JY0 + T, JY0 + T + 14, JL[1], JL[1] + 24, DOOR_WOOD)
    for c in (467, 533):                                                  # side lights
        opening('x', c - 4, c + 4, JL[1] + 6, JL[1] + 34, BAY_Y0, JY0 + T, BAY_Y0 + 4)
    for word, z0 in (("1887", 74), ("UNIVERSITY", 86), ("CLARK", 98)):
        box(464, 537, BAY_Y0 - 2, BAY_Y0, z0, z0 + 11, GRANITE)
        draw_text(word, 500, z0 + 8, BAY_Y0 - 2, GRANITE_TEXT)
    for c in (470, 500, 530):
        arch_ring('x', c - 7, c + 7, arch_z + 20, BAY_Y0 - 1, BAY_Y0, BRICK2)
        opening('x', c - 7, c + 7, arch_z, arch_z + 20, BAY_Y0, JY0 + T, BAY_Y0 + 4, arch=True)

    # ---- cornice ---------------------------------------------------------
    for k, (z0, z1) in enumerate(((J_TOP, J_TOP + 3), (J_TOP + 3, J_TOP + 6), (J_TOP + 6, J_TOP + 10))):
        p = k + 1
        box(JX0 - 2 - p, JX1 + 2 + p, JY0 - 2 - p, JY1 + 2 + p, z0, z1, TRIM)
        box(BAY_X0 - p, BAY_X1 + p, BAY_Y0 - p, JY0, z0, z1, TRIM)
    for x in range(JX0, JX1, 5):                                          # dentils
        box(x, x + 2, JY0 - 4, JY0, J_TOP - 3, J_TOP, TRIM)
        box(x, x + 2, JY1, JY1 + 4, J_TOP - 3, J_TOP, TRIM)
    box(JX0 + 3, JX1 - 3, JY0 + 3, JY1 - 3, J_TOP, J_TOP + 10, 0)         # hollow attic

    # ---- slate hipped roof (hollow shell) --------------------------------
    rz = J_TOP + 10
    rx0, rx1, ry0, ry1 = JX0 - 4, JX1 + 4, JY0 - 4, JY1 + 4
    k = 0
    while ry1 - ry0 - 4 * k > 2:
        a0, a1, b0, b1 = rx0 + 2 * k, rx1 - 2 * k, ry0 + 2 * k, ry1 - 2 * k
        box(a0, a1, b0, b1, rz + k, rz + k + 1, SLATE)
        if b1 - b0 > 12:
            box(a0 + 6, a1 - 6, b0 + 6, b1 - 6, rz + k, rz + k + 1, 0)
        k += 1
    # central pavilion with a lunette where the clock tower stood until 1924
    box(BAY_X0, BAY_X1, BAY_Y0, BAY_Y0 + 20, rz, rz + 31, BRICK)
    box(BAY_X0 - 2, BAY_X1 + 2, BAY_Y0 - 2, BAY_Y0 + 22, rz + 31, rz + 35, TRIM)
    arch_ring('x', 486, 514, rz + 11, BAY_Y0 - 1, BAY_Y0, GRANITE, thick=2)
    opening('x', 486, 514, rz + 5, rz + 11, BAY_Y0, BAY_Y0 + 6, BAY_Y0 + 3, arch=True)
    for x in (BAY_X0, BAY_X1 - 6):
        box(x, x + 6, BAY_Y0 - 1, BAY_Y0 + 21, rz, rz + 31, BRICK3)
    for x in (290, 710):                                                  # chimneys
        box(x, x + 12, 790, 802, rz + 14, rz + 61, BRICK)
        box(x - 1, x + 13, 789, 803, rz + 61, rz + 64, GRANITE)


def jch_structure():
    ix0, ix1, iy0, iy1 = JX0 + 3, JX1 - 3, JY0 + 3, JY1 - 3
    for z in JL[1:4]:
        floor_slab(ix0, ix1, iy0, iy1, z)
    floor_slab(ix0, ix1, iy0, iy1, J_TOP, wood=False)
    for lvl, (zb, zt) in enumerate(zip(JL[:4], JL[1:5])):
        top = zt - 2
        side_rooms = [x0 for k, (x0, x1) in J_ROOMS.items() if k != 'H']
        front_doors = [x0 + 14 for x0 in side_rooms] + ([] if lvl == 1 else [500])
        back_doors = [x0 + 14 for x0 in side_rooms]
        interior_wall_x(ix0, ix1, 755, zb, top, front_doors)
        interior_wall_x(ix0, ix1, 785, zb, top, back_doors)
        for x in J_CROSS:
            box(x, x + 2, iy0, 755, zb, top, PLASTER)
            box(x, x + 2, 787, iy1, zb, top, PLASTER)
        box(445, 555, 785, 787, zb, top, 0)          # stair hall open to the corridor
        if lvl == 1:
            box(445, 555, 755, 757, zb, top, 0)      # entrance hall open to the corridor
        recolor(ix0, ix1, 756, 757, zb, zb + 9, PLASTER, DOOR_WOOD)     # corridor wainscot
        recolor(ix0, ix1, 785, 786, zb, zb + 9, PLASTER, DOOR_WOOD)
        for x in range(ix0 + 40, ix1 - 20, 60):
            box(x - 4, x + 4, 769, 773, top - 1, top, LAMP)
        for i, x in enumerate((256, 346, 652, 742)):                    # notice boards
            place(bulletin_board(16, 10, lvl * 10 + i), x, 757, zb + 12, '+y')
    stairs(460, (830, 850), JL[0], JL[1], +1)                           # basement -> 1st
    stairs(535, (800, 820), JL[1], JL[2], -1)                           # 1st -> 2nd
    stairs(460, (830, 850), JL[2], JL[3], +1)                           # 2nd -> 3rd


def jch_room(key, zone, lvl):
    x0, x1 = J_ROOMS[key]
    y0, y1 = J_FRONT if zone == 'f' else J_BACK
    return Room(x0, x1, y0, y1, JL[lvl], '+y' if zone == 'f' else '-y')


# ---- room types ----------------------------------------------------------
def classroom(rm, seed=0):
    cy = (rm.y0 + rm.y1) // 2
    place(board(40, seed=seed), rm.x0, cy - 20, rm.z, '+x')
    place(teacher_desk(), rm.x0 + 8, cy - 7, rm.z, '+x')
    for rx in range(rm.x0 + 30, rm.x1 - 12, 14):
        for ry in range(rm.y0 + 6, rm.y1 - 12, 16):
            place(student_desk(), rx, ry, rm.z, '-x')
    place(painting(10, 8, 'landscape'), rm.x1 - 1, cy - 5, rm.z + 14, '-x')


def office(rm, n=1, seed=0, rug_col=RUG_BLUE):
    w, d = rm.w, rm.d
    rw, rd = min(40, w - 16), min(28, d - 24)
    rm.put(rug(rw, rd, rug_col), w // 2 - rw // 2, 4)
    us = [w // 2 - 7] if n == 1 else [w // 4 - 7, 3 * w // 4 - 7]
    for u in us:
        rm.put(office_desk(), u, 5, '+y')
        rm.put(chair(SOFA_BROWN, DOOR_WOOD), u + 5, 22, '-y')
    rm.put(bookshelf(12, 20, seed), w - 3, d // 2 - 8, '-x')
    rm.put(bookshelf(12, 20, seed + 1), w - 3, d // 2 + 5, '-x')
    rm.put(filing_cabinet(), 0, d // 2 - 2, '+x')
    rm.put(filing_cabinet(), 0, d // 2 + 3, '+x')
    rm.put(plant(), 1, 1)
    rm.put(painting(12, 10, 'landscape'), w // 2 - 6, d - 1, '+y', dz=13)


def meeting_room(rm, seed=0, chairs=BLACK_PLASTIC):
    tw = min(36, rm.w - 24)
    W, D = extent(conference_table(tw, 12))
    rm.put(conference_table(tw, 12, DOOR_WOOD, chairs), (rm.w - W) // 2, (rm.d - D) // 2)
    place(whiteboard(min(30, rm.d - 12), seed), rm.x0, (rm.y0 + rm.y1) // 2 - min(30, rm.d - 12) // 2,
          rm.z, '+x')
    place(bulletin_board(16, 10, seed), rm.x1 - 1, (rm.y0 + rm.y1) // 2 - 8, rm.z + 12, '-x')
    rm.put(plant(), rm.w - 6, 1)


def storage(rm, seed=0):
    r = np.random.default_rng(seed)
    for u in range(4, rm.w - 10, 9):
        for v in range(3, rm.d - 24, 9):
            if r.random() < 0.6:
                for k in range(int(r.integers(1, 3))):
                    rm.put(crate(7), u, v, dz=k * 7)
    rm.put(bookshelf(12, 20, seed, METAL_GRAY, (BOOK_TAN, DOOR_WOOD, BENCH_WOOD)), rm.w - 3, rm.d - 22, '-x')


def boiler_room(rm):
    x0, y0, z = rm.x0, rm.y0, rm.z
    cy = (rm.y0 + rm.y1) // 2 - 6
    box(x0 + 14, x0 + 66, cy - 8, cy + 8, z, z + 2, CONCRETE2)
    capsule((x0 + 18, cy, z + 11), (x0 + 62, cy, z + 11), 9, 9, METAL_DARK)
    box(x0 + 55, x0 + 59, cy - 2, cy + 2, z + 19, z + 23, METAL_GRAY)       # flue
    box(x0 + 2, rm.x1 - 2, rm.y1 - 8, rm.y1 - 6, z + 19, z + 21, METAL_GRAY)
    for gx in (x0 + 24, x0 + 32):
        box(gx, gx + 2, cy - 10, cy - 9, z + 12, z + 14, BRONZE_LIGHT)    # gauges
    capsule((rm.x1 - 14, rm.y1 - 18, z), (rm.x1 - 14, rm.y1 - 18, z + 18), 5, 5, STEEL)


def workshop(rm):
    rm.put(table(40, 8, BENCH_WOOD, DOOR_WOOD, 8), 4, 2)
    for u, c in ((8, METAL_DARK), (16, METAL_GRAY), (26, STEEL), (34, CHAIR_RED)):
        rm.put([(0, 3, 0, 2, 0, 2, c)], u, 4, dz=9)
    rm.put(stool(), 12, 12)
    rm.put(bookshelf(12, 20, 7, METAL_GRAY, (BOOK_TAN, METAL_DARK, CHAIR_RED)), rm.w - 3, 20, '-x')
    rm.put(crate(7), 6, 40)
    rm.put(crate(7), 6, 40, dz=7)


def archives(rm):
    for u in range(6, rm.w - 6, 6):
        for v, f in ((4, '+y'), (28, '-y'), (36, '+y')):
            rm.put(filing_cabinet(), u, v, f)


def psych_lab(rm, seed=0):
    for v in (8, 30):
        for u in (8, 48):
            rm.put(lab_bench(30), u, v)
            for k in range(3):
                rm.put(stool(), u + 5 + 9 * k, v + 10)
    place(board(40, seed=seed), rm.x0, (rm.y0 + rm.y1) // 2 - 20, rm.z, '+x')
    rm.put(display_case(16, 6, BRONZE_LIGHT), rm.w - 6, 10, '-x')


def entrance_hall(z):
    box(490, 510, 683, 800, z, z + 1, RUG_RED)                       # runner to the stairs
    box(490, 491, 683, 800, z, z + 1, BOOK_TAN)
    box(509, 510, 683, 800, z, z + 1, BOOK_TAN)
    for y in (695, 725):
        place(display_case(16, 6, BRONZE), 446, y, z, '+x')         # 1909: Freud at Clark
        place(display_case(16, 6, BRONZE_LIGHT), 548, y, z, '-x')
        place(painting(12, 14, 'portrait'), 445, y + 2, z + 20, '+x')
        place(painting(12, 14, 'portrait'), 554, y + 2, z + 20, '-x')
    for y in (705, 740):                                              # pendant lights
        box(499, 501, y - 1, y + 1, JL[2] - 8, JL[2] - 2, METAL_DARK)
        box(497, 503, y - 3, y + 3, JL[2] - 11, JL[2] - 8, LAMP)


def president_office(rm):
    rm.put(rug(60, 40, RUG_RED), 25, 4)
    rm.put(exec_desk(), 43, 6, '+y')
    rm.put(armchair(SOFA_BROWN), 40, 27, '-y')
    rm.put(armchair(SOFA_BROWN), 62, 27, '-y')
    for i, v in enumerate((4, 17, 30, 43)):
        rm.put(bookshelf(12, 24, 40 + i), 0, v, '+x')
    rm.put(sofa(20, SOFA_BROWN), 102, 30, '-x')
    rm.put(coffee_table(), 90, 35, '+x')
    rm.put(armchair(SOFA_BROWN), 76, 36, '+x')
    rm.put(painting(16, 12, 'portrait'), 109, 32, '-x', dz=14)
    rm.put(plant(), 2, 62)
    rm.put(plant(), 104, 2)
    x, y = rm.x0 + 10, rm.y0 + 60                                     # Clark scarlet flag
    box(x, x + 1, y, y + 1, rm.z, rm.z + 26, BRONZE_LIGHT)
    box(x - 1, x + 2, y - 1, y + 2, rm.z, rm.z + 1, BRONZE_LIGHT)
    box(x, x + 1, y + 1, y + 11, rm.z + 14, rm.z + 25, RUG_RED)


def seminar_room(rm, seed=0):
    W, D = extent(conference_table(48, 14))
    rm.put(conference_table(48, 14), (rm.w - W) // 2, (rm.d - D) // 2)
    place(board(40, seed=seed), rm.x1 - 2, (rm.y0 + rm.y1) // 2 - 20, rm.z, '-x')
    for i, v in enumerate((6, 19, 32, 45)):
        rm.put(bookshelf(12, 22, 60 + i), 0, v, '+x')


def reading_room(rm):
    for u in (6, 52):
        rm.put(conference_table(30, 10, BENCH_WOOD, DOOR_WOOD), u, 3)
    for u in (40, 58, 76):
        for i, v in enumerate((27, 40)):
            rm.put(bookshelf(12, 22, u + i), u - 3, v, '-x')
            rm.put(bookshelf(12, 22, u + i + 50), u, v, '+x')


def conference_room(rm, seed=0):
    W, D = extent(conference_table(48, 14))
    rm.put(conference_table(48, 14, DOOR_WOOD, SOFA_BROWN), (rm.w - W) // 2, (rm.d - D) // 2)
    place(board(40, seed=seed), rm.x0, (rm.y0 + rm.y1) // 2 - 20, rm.z, '+x')
    rm.put(plant(), rm.w - 6, 1)


def copy_room(rm):
    rm.put(copier(), 6, 3)
    rm.put(copier(), 20, 3)
    rm.put(bookshelf(12, 20, 5, METAL_GRAY, (PLASTER, WHITEBOARD, BOOK_TAN)), rm.w - 3, 10, '-x')
    rm.put(crate(6), 8, 30)
    rm.put(crate(6), 16, 30)


def furnish_jch():
    R = jch_room
    # basement
    boiler_room(R('A', 'f', 0))
    storage(R('B', 'f', 0), 1)
    workshop(R('C', 'f', 0))
    archives(R('H', 'f', 0))
    storage(R('C2', 'f', 0), 2)
    psych_lab(R('B2', 'f', 0), 3)
    psych_lab(R('A2', 'f', 0), 4)
    for i, key in enumerate(('A', 'B', 'C', 'C2', 'B2', 'A2')):
        storage(R(key, 'b', 0), 10 + i)
    # first floor
    entrance_hall(JL[1])
    for i, key in enumerate(('A', 'B', 'B2', 'A2')):
        classroom(R(key, 'f', 1), i)
        classroom(R(key, 'b', 1), 10 + i)
    for i, key in enumerate(('C', 'C2')):
        office(R(key, 'f', 1), 1, 20 + i)
        office(R(key, 'b', 1), 1, 30 + i, CARPET2)
    # second floor
    president_office(R('H', 'f', 2))
    for i, key in enumerate(('C', 'C2')):
        office(R(key, 'f', 2), 1, 40 + i)
        copy_room(R(key, 'b', 2))
    for i, key in enumerate(('A', 'B', 'A2')):
        office(R(key, 'f', 2), 2, 50 + i, (RUG_BLUE, CARPET2, RUG_RED)[i])
    conference_room(R('B2', 'f', 2), 5)
    for i, key in enumerate(('A', 'B', 'B2', 'A2')):
        classroom(R(key, 'b', 2), 60 + i)
    # third floor
    seminar_room(R('H', 'f', 3), 7)
    reading_room(R('A2', 'f', 3))
    for i, key in enumerate(('A', 'B', 'B2')):
        classroom(R(key, 'f', 3), 70 + i)
    for i, key in enumerate(('A', 'B', 'B2', 'A2')):
        classroom(R(key, 'b', 3), 80 + i)
    for i, key in enumerate(('C', 'C2')):
        office(R(key, 'f', 3), 1, 90 + i)
        office(R(key, 'b', 3), 1, 95 + i, CARPET2)
    # ceiling lights everywhere
    for lvl in range(4):
        ceil = JL[lvl + 1] - 2
        for key, (x0, x1) in J_ROOMS.items():
            for (y0, y1) in (J_FRONT, J_BACK):
                ceiling_lights(x0, x1, y0, y1, ceil, 2 if x1 - x0 > 70 else 1)


# --------------------------------------------------------------------------
# Higgins University Center (to the right of Jonas Clark Hall, also facing
# Main Street).  Tilton Hall, the "Great Room" with its vaulted ceiling,
# fills the pavilion on the second floor.
# --------------------------------------------------------------------------
UX0, UX1, UY0, UY1 = 860, 1300, 690, 880
PX0, PX1, PY0 = 1000, 1160, 672             # Tilton Hall pavilion
UL = [1, 41, 81, 121, 161]
U_TOP = 170
HALL_Y1 = 800                                # back wall of Tilton Hall / corridor


def university_center():
    T = 3
    box(UX0, UX1, PY0, UY1, 0, 1, CONCRETE)
    shell(UX0, UX1, UY0, UY1, 1, U_TOP, UC_BRICK, T)
    box(PX0, PX1, PY0, UY0 + T, 1, U_TOP, UC_BRICK)
    box(PX0 + T, PX1 - T, PY0 + T, UY0 + T, 1, U_TOP, 0)
    for z in (UL[1] - 2, UL[2] - 2, UL[3] - 2):                       # precast bands
        box(UX0 - 1, UX1 + 1, UY0 - 1, UY1 + 1, z, z + 3, CONCRETE_LIGHT)
        box(PX0 - 1, PX1 + 1, PY0 - 1, UY0, z, z + 3, CONCRETE_LIGHT)
        box(UX0 + T, UX1 - T, UY0 + T, UY1 - T, z, z + 3, 0)
        box(PX0 + T, PX1 - T, PY0 + T, UY0 + T, z, z + 3, 0)
    box(UX0 - 2, UX1 + 2, UY0 - 2, UY1 + 2, UL[4], UL[4] + 4, CONCRETE_LIGHT)   # cornice
    box(UX0 - 3, UX1 + 3, UY0 - 3, UY1 + 3, UL[4] + 4, U_TOP, CONCRETE_LIGHT)
    box(PX0 - 2, PX1 + 2, PY0 - 2, UY0, UL[4], UL[4] + 4, CONCRETE_LIGHT)
    box(PX0 - 3, PX1 + 3, PY0 - 3, UY0, UL[4] + 4, U_TOP, CONCRETE_LIGHT)
    box(UX0 + T, UX1 - T, UY0 + T, UY1 - T, UL[4], U_TOP, 0)
    box(PX0 + T, PX1 - T, PY0 + T, UY0 + T, UL[4], U_TOP, 0)
    recolor(UX0 - 2, UX1 + 2, PY0 - 2, UY1 + 2, 1, 8, UC_BRICK, GRANITE_DARK)   # base

    def win(axis, c, z0, z1, d0, d1, gd, out_d):
        a0, a1 = c - 7, c + 7
        opening(axis, a0, a1, z0, z1, d0, d1, gd)
        if axis == 'x':
            box(a0 - 1, a1 + 1, out_d, out_d + 1, z0 - 2, z0, CONCRETE_LIGHT)
            box(a0 - 1, a1 + 1, out_d, out_d + 1, z1, z1 + 3, UC_BRICK2)
            box(c, c + 1, gd, gd + 1, z0, z1, METAL_DARK)
        else:
            box(out_d, out_d + 1, a0 - 1, a1 + 1, z0 - 2, z0, CONCRETE_LIGHT)
            box(out_d, out_d + 1, a0 - 1, a1 + 1, z1, z1 + 3, UC_BRICK2)
            box(gd, gd + 1, c, c + 1, z0, z1, METAL_DARK)

    wz = [(10, 34), (UL[1] + 8, UL[1] + 30), (UL[2] + 8, UL[2] + 30), (UL[3] + 8, UL[3] + 28)]
    for z0, z1 in wz:
        for c in (888, 920, 952, 984, 1176, 1208, 1240, 1272):
            win('x', c, z0, z1, UY0, UY0 + T, UY0 + 1, UY0 - 1)
        for c in (885, 915, 965, 997, 1035, 1067, 1105, 1137, 1175, 1207, 1246, 1278):
            win('x', c, z0, z1, UY1 - T, UY1, UY1 - 2, UY1)
        for c in (710, 742, 774, 816, 855):
            win('y', c, z0, z1, UX0, UX0 + T, UX0 + 1, UX0 - 1)
            win('y', c, z0, z1, UX1 - T, UX1, UX1 - 2, UX1)

    # ---- Tilton Hall windows: three tall arched windows ------------------
    for c in (1035, 1080, 1125):
        arch_ring('x', c - 9, c + 9, 122, PY0 - 1, PY0, CONCRETE_LIGHT, thick=2)
        opening('x', c - 9, c + 9, 52, 122, PY0, PY0 + T, PY0 + 1, arch=True)
        box(c, c + 1, PY0 + 1, PY0 + 2, 52, 131, METAL_DARK)
        for z in (72, 97, 122):
            box(c - 9, c + 9, PY0 + 1, PY0 + 2, z, z + 1, METAL_DARK)
        box(c - 10, c + 10, PY0 - 1, PY0, 50, 52, CONCRETE_LIGHT)

    # ---- glass storefront, doors and canopy ------------------------------
    opening('x', PX0 + 14, PX1 - 14, 1, 34, PY0, PY0 + T, PY0 + 1)
    for x in range(PX0 + 14, PX1 - 13, 13):
        box(x, x + 1, PY0 + 1, PY0 + 2, 1, 34, METAL_DARK)
    box(PX0 + 14, PX1 - 14, PY0 + 1, PY0 + 2, 24, 25, METAL_DARK)
    box(1066, 1094, PY0, PY0 + T, 1, 24, 0)
    box(1065, 1066, PY0, PY0 + T, 1, 25, METAL_DARK)
    box(1094, 1095, PY0, PY0 + T, 1, 25, METAL_DARK)
    box(PX0 + 5, PX1 - 5, PY0 - 25, PY0, 34, 36, METAL_GRAY)
    box(PX0 + 5, PX1 - 5, PY0 - 27, PY0 - 25, 30, 40, CONCRETE_LIGHT)
    draw_text("HIGGINS UNIVERSITY CENTER", 1080, 38, PY0 - 28, METAL_DARK)
    for x in (PX0 + 10, PX1 - 13):
        box(x, x + 3, PY0 - 24, PY0 - 21, 1, 34, METAL_DARK)

    # ---- hipped metal roof, then the pavilion gable on top of it ---------
    rx0, rx1, ry0, ry1 = UX0 - 4, UX1 + 4, UY0 - 4, UY1 + 4
    k = 0
    while ry1 - ry0 - 4 * k > 2:
        a0, a1, b0, b1 = rx0 + 2 * k, rx1 - 2 * k, ry0 + 2 * k, ry1 - 2 * k
        box(a0, a1, b0, b1, U_TOP + k, U_TOP + k + 1, ROOF_METAL)
        if b1 - b0 > 12:
            box(a0 + 6, a1 - 6, b0 + 6, b1 - 6, U_TOP + k, U_TOP + k + 1, 0)
        k += 1
    k = 0
    while (PX1 + 4 - 2 * k) - (PX0 - 4 + 2 * k) > 4:
        xa, xb, z = PX0 - 4 + 2 * k, PX1 + 4 - 2 * k, U_TOP + k
        box(xa, xa + 4, PY0 - 4, 790, z, z + 1, ROOF_METAL)
        box(xb - 4, xb, PY0 - 4, 790, z, z + 1, ROOF_METAL)
        box(xa + 4, xb - 4, PY0, PY0 + 3, z, z + 1, UC_BRICK)           # pediment
        box(xa, xa + 4, PY0 - 4, PY0, z, z + 1, CONCRETE_LIGHT)         # raking cornice
        box(xb - 4, xb, PY0 - 4, PY0, z, z + 1, CONCRETE_LIGHT)
        k += 1
    oz = U_TOP + 16                                                     # oculus
    for x in range(1069, 1092):
        for z in range(oz - 10, oz + 11):
            d = math.hypot(x + 0.5 - 1080, z + 0.5 - oz)
            if d < 7:
                box(x, x + 1, PY0, PY0 + 3, z, z + 1, 0)
                box(x, x + 1, PY0 + 1, PY0 + 2, z, z + 1, GLASS)
            elif d < 9.5:
                box(x, x + 1, PY0 - 1, PY0 + 3, z, z + 1, CONCRETE_LIGHT)


def uc_structure():
    ix0, ix1, iy0, iy1 = UX0 + 3, UX1 - 3, UY0 + 3, UY1 - 3
    box(ix0, ix1, iy0, iy1, 0, 1, TILE)
    box(PX0 + 3, PX1 - 3, PY0 + 3, iy0, 0, 1, TILE)
    for z in UL[1:4]:
        floor_slab(ix0, ix1, iy0, iy1, z, wood=False)
        box(ix0, ix1, iy0, iy1, z - 1, z, CARPET)
    floor_slab(PX0 + 3, PX1 - 3, PY0 + 3, iy0, UL[1], wood=False)
    floor_slab(ix0, ix1, iy0, iy1, UL[4], wood=False)
    floor_slab(PX0 + 3, PX1 - 3, PY0 + 3, iy0, UL[4], wood=False)
    for z in (UL[2], UL[3]):                                  # Tilton Hall is 3 storeys tall
        box(PX0 + 2, PX1 - 2, iy0, HALL_Y1, z - 2, z, 0)
    box(PX0 + 2, PX1 - 2, iy0, HALL_Y1, UL[1] - 1, UL[1], FLOOR_WOOD)
    box(PX0 + 3, PX1 - 3, PY0 + 3, iy0, UL[1] - 1, UL[1], FLOOR_WOOD)

    for lvl, (zb, zt) in enumerate(zip(UL[:4], UL[1:5])):
        top = zt - 2
        fdoors = {0: [975, 1174], 1: [877, 1020, 1140, 1174]}.get(lvl, [877, 946, 1174, 1244])
        interior_wall_x(ix0, ix1, HALL_Y1, zb, top, fdoors)
        if lvl == 0:
            box(1040, 1120, HALL_Y1, HALL_Y1 + 2, zb, zb + 28, 0)      # lobby -> corridor
        bdoors = [961, 1031, 1101, 1180, 1250] if lvl == 0 else [961, 1031, 1101, 1171, 1241]
        interior_wall_x(945, ix1, 830, zb, top, bdoors)
        for x in (945, 1015, 1085, 1155, 1225):
            if not (lvl == 0 and x == 1225):                            # kitchen is one room
                box(x, x + 2, 832, iy1, zb, top, PLASTER)
        if lvl >= 2:
            box(930, 932, iy0, HALL_Y1, zb, top, PLASTER)
            box(1228, 1230, iy0, HALL_Y1, zb, top, PLASTER)
        recolor(ix0, ix1, HALL_Y1 + 1, HALL_Y1 + 2, zb, zb + 9, PLASTER, DOOR_WOOD)
        recolor(ix0, ix1, 830, 831, zb, zb + 9, PLASTER, DOOR_WOOD)
        for x in range(ix0 + 20, ix1, 60):
            box(x - 4, x + 4, 814, 818, top - 1, top, LAMP)
        for i, x in enumerate((900, 1060, 1190)):
            place(bulletin_board(16, 10, 100 + lvl * 10 + i), x, 829, zb + 12, '-y')
    # lobby walls with wide openings to the Bistro and the dining room
    for x in (PX0, PX1 - 2):
        box(x, x + 2, iy0, HALL_Y1, UL[0], UL[1] - 2, PLASTER)
        box(x, x + 2, 720, 770, UL[0], UL[0] + 30, 0)
    # Tilton Hall: cream walls, wood wainscot, doors, barrel vault
    for x in (PX0, PX1 - 2):
        box(x, x + 2, iy0, HALL_Y1, UL[1], UL[4] - 2, WALL_CREAM)
        box(x, x + 2, 782, 794, UL[1], UL[1] + 24, 0)
    box(PX0, PX1, HALL_Y1, HALL_Y1 + 2, UL[1], UL[4] - 2, WALL_CREAM)
    for dx in (1020, 1140):
        box(dx - 7, dx + 7, HALL_Y1, HALL_Y1 + 2, UL[1], UL[1] + 25, DOOR_WOOD)
        box(dx - 6, dx + 6, HALL_Y1, HALL_Y1 + 2, UL[1], UL[1] + 24, 0)
    recolor(PX0 + 1, PX0 + 2, iy0, HALL_Y1, UL[1], UL[1] + 12, WALL_CREAM, DOOR_WOOD)
    recolor(PX1 - 2, PX1 - 1, iy0, HALL_Y1, UL[1], UL[1] + 12, WALL_CREAM, DOOR_WOOD)
    recolor(PX0, PX1, HALL_Y1, HALL_Y1 + 1, UL[1], UL[1] + 12, WALL_CREAM, DOOR_WOOD)
    xc, R, zs = 1080, 78, 77
    xs = np.arange(PX0 + 2, PX1 - 2) + 0.5
    zz = np.arange(zs, UL[4] - 2) + 0.5
    m = np.hypot(xs[:, None] - xc, zz[None, :] - zs)
    m = (m >= R) & (m < R + 3)
    for y in range(PY0 + 3, HALL_Y1):
        G[PX0 + 2:PX1 - 2, y, zs:UL[4] - 2][m] = PLASTER
    # stairs (switchback) at the west end
    stairs(870, (835, 855), UL[0], UL[1], +1)
    stairs(930, (857, 876), UL[1], UL[2], -1, rails=('-y',))
    stairs(870, (835, 855), UL[2], UL[3], +1)


def lobby(z):
    disc(1080, 735, 18, z, z + 1, RUG_RED)
    c_letter(1080, 735, z, 7, 12, WHITEBOARD)
    place(counter(40, 7, DOOR_WOOD, GRANITE), 1060, 772, z, '-y')     # information desk
    place(office_chair(), 1066, 781, z, '-y')
    place(office_chair(), 1088, 781, z, '-y')
    for x0 in (1008, 1124):
        place(sofa(20, SOFA_GREEN), x0, 700, z, '+x')
        place(coffee_table(), x0 + 11, 705, z, '+x')
        place(sofa(20, SOFA_GREEN), x0 + 20, 700, z, '-x')
    for x, y in ((1004, 676), (1151, 676), (1004, 790), (1151, 790)):
        place(plant(12), x, y, z)
    place(tv(30), 1065, 797, z + 12, '-y')                             # events screen


def bistro(z):
    place(counter(70, 8, DOOR_WOOD, GRANITE), 875, 778, z, '-y')
    box(880, 888, 781, 785, z + 11, z + 17, STEEL)                    # espresso machine
    box(900, 920, 779, 785, z + 11, z + 16, GLASS)                    # pastry case
    box(901, 919, 780, 784, z + 11, z + 15, 0)
    box(902, 918, 781, 783, z + 11, z + 12, BOOK_TAN)
    box(880, 940, 799, 800, z + 18, z + 30, BLACK_PLASTIC)            # menu board
    for zz in (z + 27, z + 24, z + 21):
        box(884, 930, 798, 799, zz, zz + 1, PLASTER)
    for x in range(878, 942, 8):
        place(stool(CHAIR_RED, 7), x, 770, z)
    for x in (872, 906, 940):
        for y in (702, 726, 750):
            place(cafe_set(CHAIR_RED if (x + y) % 2 else CHAIR_BLUE), x, y, z)
    place(plant(12), 990, 696, z)


def dining_hall(z):
    place(serving_line(90), 1195, 784, z, '-y')
    for x in (1172, 1232):
        for y in (700, 728, 756):
            place(dining_table(36), x, y, z)
    place(plant(12), 1290, 696, z)


def kitchen(z):
    place(counter(60, 7, STEEL, STEEL), 1162, 870, z, '+y')
    for x in (1230, 1240, 1250):
        place(stove(), x, 869, z, '+y')
    for y in (838, 848, 858):
        place(fridge(), 1288, y, z, '-x')
    place(table(30, 10, STEEL, STEEL, 8), 1200, 846, z)


def tilton_hall(z):
    box(PX0 + 3, 1040, 700, 778, z, z + 6, FLOOR_WOOD)               # stage
    box(1039, 1040, 700, 778, z, z + 6, DOOR_WOOD)
    box(1040, 1044, 732, 746, z, z + 3, FLOOR_WOOD)                  # steps
    place(grand_piano(), 1010, 745, z + 6, '-y')
    place(podium(), 1030, 712, z + 6, '+x')
    # granite fireplace on the back wall
    box(1058, 1102, 791, HALL_Y1, z, z + 36, GRANITE)
    box(1068, 1092, 791, 797, z, z + 20, 0)
    box(1068, 1092, 797, HALL_Y1, z, z + 20, GRANITE_TEXT)
    box(1072, 1088, 793, 796, z, z + 2, TRUNK)
    box(1054, 1106, 789, HALL_Y1, z + 22, z + 25, GRANITE_DARK)
    box(1062, 1098, 794, HALL_Y1, z + 36, 150, GRANITE)
    box(1062, 1098, 783, 791, z, z + 1, GRANITE_DARK)
    for x in (1062, 1098, 1134):
        for y in (702, 745):
            round_table(x, y, z)
    for x in (1040, 1080, 1120):                                      # chandeliers
        zv = 77 + math.sqrt(78 ** 2 - (x + 0.5 - 1080) ** 2)
        box(x, x + 1, 737, 738, 118, int(zv), METAL_DARK)
        disc(x + 0.5, 737.5, 6, 116, 117, BRONZE_LIGHT)
        box(x - 1, x + 2, 736, 739, 112, 116, LAMP)
        for a in range(8):
            px = x + 0.5 + 5.5 * math.cos(a * math.pi / 4)
            py = 737.5 + 5.5 * math.sin(a * math.pi / 4)
            box(int(px), int(px) + 1, int(py), int(py) + 1, 117, 119, LAMP)
    for y in (705, 740):
        place(painting(14, 18, 'portrait'), PX1 - 3, y, z + 22, '-x')
        place(painting(14, 18, 'landscape'), PX0 + 2, y, z + 30, '+x')


def mailroom(z):
    place(mailboxes(80, 24), PX0 - 1, 700, z, '-x')
    place(counter(40, 7), 890, 750, z, '+y')
    for x in (890, 904, 918):
        place(bookshelf(12, 20, x, METAL_GRAY, (BOOK_TAN, DOOR_WOOD, BENCH_WOOD)), x, 696, z, '+y')
    place(bulletin_board(20, 12, 3), 863, 760, z + 12, '+x')
    place(bench(16), 940, 770, z, '-y')
    place(plant(12), 990, 696, z)


def lounge(z):
    rm = Room(PX1, UX1 - 3, UY0 + 3, HALL_Y1, z, '+y')
    rm.put(rug(70, 50, RUG_BLUE), 40, 20)
    place(tv(24), UX1 - 4, 730, z + 10, '-x')
    rm.put(sofa(24, SOFA_GREEN), 92, 30, '+x')
    rm.put(coffee_table(), 106, 37, '+x')
    rm.put(sofa(20, SOFA_BROWN), 20, 4, '+y')
    rm.put(coffee_table(), 25, 17)
    rm.put(sofa(20, SOFA_BROWN), 20, 26, '-y')
    rm.put(armchair(SOFA_GREEN), 60, 64, '+x')
    rm.put(armchair(SOFA_GREEN), 76, 64, '-x')
    rm.put(ping_pong(), 50, 80)
    rm.put(bookshelf(12, 20, 77, DOOR_WOOD), 0, 40, '+x')
    for u, v in ((2, 2), (130, 2), (130, 98)):
        rm.put(plant(12), u, v)


def game_room(rm):
    rm.put(pool_table(), (rm.w - 25) // 2, 12)
    for u in (4, 13, 22):
        rm.put(arcade(), u, 0, '+y')


def vending_room(rm):
    for u, c in ((6, CHAIR_RED), (17, CHAIR_BLUE), (28, BOOK_GREEN)):
        rm.put(vending(c), u, 0, '+y')
    rm.put(cafe_set(), 30, 18)
    rm.put(plant(12), rm.w - 6, 1)


def newsroom(rm, seed=0):
    office(rm, 2, seed, CARPET2)
    rm.put(table(24, 10, BENCH_WOOD, METAL_DARK), rm.w // 2 - 12, rm.d // 2 + 6)
    for u in range(rm.w // 2 - 10, rm.w // 2 + 10, 4):
        rm.put([(0, 3, 0, 4, 0, 1, PLASTER)], u, rm.d // 2 + 9, dz=8)


def furnish_uc():
    z0, z1, z2, z3 = UL[:4]
    lobby(z0)
    bistro(z0)
    dining_hall(z0)
    kitchen(z0)
    back = [(947, 1015), (1017, 1085), (1087, 1155), (1157, 1225), (1227, 1297)]

    def B(i, z):
        return Room(back[i][0], back[i][1], 832, UY1 - 3, z, '-y')

    game_room(B(0, z0))
    storage(B(1, z0), 41)
    vending_room(B(2, z0))
    tilton_hall(z1)
    mailroom(z1)
    lounge(z1)
    for i in range(5):
        meeting_room(B(i, z1), 110 + i)
    wings = [(863, 930), (932, 1000), (1160, 1228), (1230, 1297)]
    for i, (x0, x1) in enumerate(wings):
        rm2 = Room(x0, x1, UY0 + 3, HALL_Y1, z2, '+y')
        rm3 = Room(x0, x1, UY0 + 3, HALL_Y1, z3, '+y')
        if i < 2:
            meeting_room(rm2, 120 + i, CHAIR_RED)
        elif i == 2:
            office(rm2, 2, 130, RUG_RED)          # student government
        else:
            newsroom(rm2, 131)                    # The Scarlet
        office(rm3, 2, 140 + i, (RUG_BLUE, CARPET2, RUG_RED, RUG_BLUE)[i])
    for i in range(5):
        office(B(i, z2), 1, 150 + i)
        office(B(i, z3), 1, 160 + i, CARPET2)
    for lvl in range(4):
        ceil = UL[lvl + 1] - 2
        for (x0, x1) in back:
            ceiling_lights(x0, x1, 832, UY1 - 3, ceil, 2)
        if lvl == 0:
            for x0, x1 in ((863, 1000), (1003, 1157), (1160, 1297)):
                ceiling_lights(x0, x1, UY0 + 3, HALL_Y1, ceil, 3)
        elif lvl == 1:
            for x0, x1 in ((863, 1000), (1160, 1297)):
                ceiling_lights(x0, x1, UY0 + 3, HALL_Y1, ceil, 3)
        else:
            for x0, x1 in wings:
                ceiling_lights(x0, x1, UY0 + 3, HALL_Y1, ceil, 1)


# --------------------------------------------------------------------------
# Main Street, the campus fence and the gates
# --------------------------------------------------------------------------
FENCE_Y = 186
LAWN_Y0 = 189
GATE_X0, GATE_X1 = 478, 522                  # main gate, on Jonas Clark Hall's axis
UCG_X0, UCG_X1 = 1068, 1092                  # pedestrian gate to the University Center


def street_lamp(x, y, toward):
    box(x - 1, x + 3, y - 1, y + 3, 2, 6, METAL_DARK)
    box(x, x + 2, y, y + 2, 2, 82, METAL_DARK)
    ye = y + toward * 26
    box(x, x + 2, min(y, ye), max(y, ye) + 2, 80, 82, METAL_DARK)
    box(x - 2, x + 4, ye - 3, ye + 5, 76, 80, METAL_GRAY)
    box(x - 1, x + 3, ye - 2, ye + 4, 75, 76, LAMP)


def main_street():
    box(0, NX, 0, 28, 0, 2, CONCRETE)                 # far sidewalk
    box(0, NX, 28, 30, 0, 2, GRANITE)                 # curbs
    box(0, NX, 150, 152, 0, 2, GRANITE)
    box(0, NX, 30, 150, 0, 1, ASPHALT)
    box(0, NX, 152, 183, 0, 2, CONCRETE)              # near sidewalk
    for x in range(0, NX, 15):
        box(x, x + 1, 0, 28, 1, 2, CONCRETE2)
        box(x, x + 1, 152, 183, 1, 2, CONCRETE2)
    box(0, NX, 88, 89, 0, 1, PAINT_YELLOW)           # double yellow centre line
    box(0, NX, 91, 92, 0, 1, PAINT_YELLOW)
    box(0, NX, 50, 51, 0, 1, PAINT_WHITE)            # parking lanes
    box(0, NX, 129, 130, 0, 1, PAINT_WHITE)
    box(486, 514, 30, 150, 0, 1, ASPHALT)            # crosswalk to the main gate
    for y in range(34, 146, 12):
        box(486, 514, y, y + 6, 0, 1, PAINT_WHITE)
    box(486, 514, 150, 158, 1, 2, 0)                 # curb ramps
    box(486, 514, 22, 30, 1, 2, 0)
    box(486, 514, 150, 152, 0, 1, CONCRETE)
    box(486, 514, 28, 30, 0, 1, CONCRETE)
    for x in range(120, NX, 300):
        disc(x, 70, 3.5, 0, 1, METAL_DARK)          # manholes
    for x in range(200, NX, 400):
        box(x, x + 8, 146, 150, 0, 1, METAL_DARK)   # storm drains
        box(x, x + 8, 30, 34, 0, 1, METAL_DARK)
    for x in (140, 390, 640, 890, 1140, 1340):
        street_lamp(x, 156, -1)
    for x in (265, 765, 1265):
        street_lamp(x, 12, +1)
    disc(330.5, 160.5, 2.2, 2, 9, HYDRANT_RED)        # fire hydrant
    disc(330.5, 160.5, 1.6, 9, 11, HYDRANT_RED)
    box(326, 335, 160, 161, 6, 8, HYDRANT_RED)
    box(840, 846, 162, 167, 3, 13, MAILBOX_BLUE)      # mailbox
    box(840, 846, 163, 166, 13, 14, MAILBOX_BLUE)
    box(841, 845, 161, 162, 10, 11, METAL_DARK)
    for a, b in ((840, 162), (845, 162), (840, 166), (845, 166)):
        box(a, a + 1, b, b + 1, 2, 3, METAL_DARK)


def campus_fence():
    y = FENCE_Y
    xs, xe = 20, NX - 20
    gaps = [(GATE_X0, GATE_X1), (UCG_X0, UCG_X1)]
    box(xs, xe, 183, 189, 0, 3, GRANITE)
    for a, b in gaps:
        box(a, b, 183, 189, 0, 3, 0)
        pavers(a, b, 183, 189)
    piers = [(GATE_X0 - 14, 14, 36, True), (GATE_X1, 14, 36, True),
             (UCG_X0 - 12, 12, 28, True), (UCG_X1, 12, 28, True)]
    for px in list(range(xs, xe - 20, 120)) + [xe - 10]:
        if all(abs(px - g) > 40 for g in (GATE_X0, GATE_X1, UCG_X0, UCG_X1)):
            piers.append((px, 10, 24, False))
    blocked = np.zeros(NX, dtype=bool)
    for a, b in gaps:
        blocked[a:b] = True
    for px, w, h, finial in piers:
        y0 = y - w // 2
        box(px, px + w, y0, y0 + w, 0, h, BRICK)
        box(px - 1, px + w + 1, y0 - 1, y0 + w + 1, h, h + 3, GRANITE)
        if finial:
            ball(px + w / 2, y + 0.5, h + 6, 3.2, GRANITE)
        blocked[max(0, px):px + w] = True
    for x in range(xs, xe):
        if blocked[x]:
            continue
        if x % 3 == 0:
            box(x, x + 1, y, y + 1, 3, 19, METAL_DARK)
        box(x, x + 1, y, y + 1, 5, 6, METAL_DARK)
        box(x, x + 1, y, y + 1, 16, 17, METAL_DARK)
    # arch over the main gate with a gold "C" medallion
    for x in range(GATE_X0, GATE_X1):
        t = (x + 0.5 - GATE_X0) / (GATE_X1 - GATE_X0)
        za = 36 + int(round(10 * math.sin(math.pi * t)))
        box(x, x + 1, y - 1, y + 1, za, za + 2, METAL_DARK)
        if (x - GATE_X0) % 4 == 2:
            box(x, x + 1, y, y + 1, 32, za, METAL_DARK)
    box(GATE_X0, GATE_X1, y, y + 1, 32, 33, METAL_DARK)
    mx, mz = (GATE_X0 + GATE_X1) / 2, 54
    for x in range(int(mx) - 9, int(mx) + 10):
        for z in range(mz - 9, mz + 10):
            if 7 <= math.hypot(x + 0.5 - mx, z + 0.5 - mz) < 8.4:
                box(x, x + 1, y - 1, y + 1, z, z + 1, METAL_DARK)
    c_letter(mx, mz, 0, 3.6, 6.2, BRONZE_LIGHT, plane='xz', y_plane=(y - 1, y + 1))

    # open gate leaves (swung inwards)
    def leaf(x, length, h):
        for yy in range(LAWN_Y0 + 1, LAWN_Y0 + 1 + length, 2):
            box(x, x + 1, yy, yy + 1, 3, h, METAL_DARK)
        for z in (4, h // 2, h - 1):
            box(x, x + 1, LAWN_Y0 + 1, LAWN_Y0 + 1 + length, z, z + 1, METAL_DARK)
    leaf(GATE_X0, 22, 30)
    leaf(GATE_X1 - 1, 22, 30)
    leaf(UCG_X0, 12, 22)
    leaf(UCG_X1 - 1, 12, 22)


# --------------------------------------------------------------------------
# The Green: lawn, walks, Red Square, plazas, lamps, benches, flower beds
# --------------------------------------------------------------------------
def ground():
    G[:, LAWN_Y0:, 0] = GRASS
    thick_line(486, 225, 190, 640, 14, 0, CONCRETE)               # diagonal walks
    thick_line(514, 225, 1000, 612, 14, 0, CONCRETE)
    box(486, 514, LAWN_Y0, 560, 0, 1, GRANITE_DARK)              # main walk, brick
    pavers(488, 512, LAWN_Y0, 560)
    box(1066, 1094, LAWN_Y0, 640, 0, 1, GRANITE_DARK)            # walk to the UC
    box(1068, 1092, LAWN_Y0, 640, 0, 1, CONCRETE)
    box(180, 820, 640, JY0, 0, 1, CONCRETE)                       # sidewalks round JCH
    box(180, 200, 640, 880, 0, 1, CONCRETE)
    box(180, 820, JY1, 880, 0, 1, CONCRETE)
    box(800, 860, 640, 900, 0, 1, CONCRETE)                       # alley between the two
    box(840, 1320, 640, UY0, 0, 1, CONCRETE)                      # sidewalks round the UC
    box(UX1, 1320, 640, 900, 0, 1, CONCRETE)
    box(840, 1320, UY1, 900, 0, 1, CONCRETE)
    pavers(360, 640, 560, 640)                                    # Red Square
    pavers(440, 560, 640, JY0)
    pavers(640, 990, 600, 628)                                    # brick walk to the UC
    pavers(990, 1170, 600, PY0)                                   # UC plaza
    for x0, x1 in ((205, 455), (545, 795)):                       # foundation beds
        box(x0, x1, 669, JY0, 0, 1, MULCH)
    for x0, x1 in ((865, 995), (1165, 1295)):
        box(x0, x1, 680, UY0, 0, 1, MULCH)


def lawn_lamp(x, y):
    box(x, x + 2, y, y + 2, 1, 38, METAL_DARK)
    box(x - 1, x + 3, y - 1, y + 3, 1, 3, METAL_DARK)
    box(x - 1, x + 3, y - 1, y + 3, 38, 43, LAMP)
    box(x - 2, x + 4, y - 2, y + 4, 43, 44, METAL_DARK)


def landscape():
    for y in (270, 390, 510):
        lawn_lamp(479, y)
        lawn_lamp(519, y)
    for y in (300, 450):
        lawn_lamp(1058, y)
        lawn_lamp(1100, y)
    for x in (380, 620):
        lawn_lamp(x, 600)
    for x in (700, 900):
        lawn_lamp(x, 631)
    for y in (330, 460):
        place(bench(16), 474, y, 1, '+x')
        place(bench(16), 521, y, 1, '-x')
        place(trash_can(), 474, y + 18, 1)
    place(bench(16), 395, 590, 1, '-y')
    place(bench(16), 588, 590, 1, '-y')
    for i in range(5):                                            # bike rack at the UC
        x = 1232 + 6 * i
        box(x, x + 1, 645, 646, 1, 9, METAL_GRAY)
        box(x, x + 1, 651, 652, 1, 9, METAL_GRAY)
        box(x, x + 1, 645, 652, 8, 9, METAL_GRAY)
    r = np.random.default_rng(5)
    for x0, x1, yc in ((208, 452, 674), (548, 792, 674), (868, 992, 685), (1168, 1292, 685)):
        for x in range(x0 + 6, x1 - 4, 15):
            leaf_blob(x + r.uniform(-2, 2), yc, 5, 7, 5, 6, (SHRUB, SHRUB2), r, 0.9, 7)


# --------------------------------------------------------------------------
# Sigmund Freud statue: bronze Freud seated on a low granite wall, reading
# --------------------------------------------------------------------------
FREUD_X, FREUD_Y, WALL_Y1 = 425, 560, 568


def freud_statue():
    S = 1.8                     # statue is slightly larger than life
    seat_z = 10                 # wall top
    for x0, x1 in ((370, 482), (518, 630)):
        box(x0, x1, FREUD_Y, WALL_Y1, 1, seat_z - 1, GRANITE)
        box(x0 - 1, x1 + 1, FREUD_Y - 1, WALL_Y1 + 1, seat_z - 1, seat_z, GRANITE_DARK)
        box(x0, x1, WALL_Y1 + 1, WALL_Y1 + 8, 1, 2, DIRT)
        box(x0 + 2, x1 - 2, WALL_Y1 + 1, WALL_Y1 + 7, 2, 8, SHRUB2)   # low hedge

    ox, oy, oz = FREUD_X, FREUD_Y, seat_z
    parts = [
        ('ell', (0, 2.0, 1.0), (2.2, 2.0, 1.3), BRONZE),                 # pelvis
        ('cap', (-1.0, 1.4, 1.1), (-1.0, -3.4, 1.3), 0.95, BRONZE),       # thighs
        ('cap', (1.0, 1.4, 1.1), (1.0, -3.4, 1.3), 0.95, BRONZE),
        ('cap', (-1.0, -3.5, 1.0), (-1.0, -3.9, -4.4), 0.75, BRONZE),     # shins
        ('cap', (1.0, -3.5, 1.0), (1.0, -3.9, -4.4), 0.75, BRONZE),
        ('ell', (-1.0, -4.6, -4.7), (0.7, 1.3, 0.45), BRONZE_DARK),       # shoes
        ('ell', (1.0, -4.6, -4.7), (0.7, 1.3, 0.45), BRONZE_DARK),
        ('ell', (0, 1.7, 3.6), (2.1, 1.5, 2.6), BRONZE),                  # torso
        ('cap', (-2.0, 1.6, 5.4), (2.0, 1.6, 5.4), 0.85, BRONZE),         # shoulders
        ('cap', (-2.3, 1.6, 5.2), (-2.0, -0.1, 2.5), 0.65, BRONZE),       # upper arms
        ('cap', (2.3, 1.6, 5.2), (2.0, -0.1, 2.5), 0.65, BRONZE),
        ('cap', (-2.0, -0.1, 2.5), (-1.0, -2.3, 2.9), 0.6, BRONZE),       # forearms
        ('cap', (2.0, -0.1, 2.5), (1.0, -2.3, 2.9), 0.6, BRONZE),
        ('box', (-1.7, -3.1, 2.6), (1.7, -1.3, 3.1), BRONZE_LIGHT),       # open book
        ('box', (-0.15, -3.1, 2.4), (0.15, -1.3, 3.0), BRONZE_DARK),      # spine
        ('cap', (0, 1.5, 6.0), (0, 1.2, 6.9), 0.6, BRONZE),               # neck
        ('ell', (0, 0.9, 7.9), (1.0, 1.15, 1.25), BRONZE),                # head
        ('ell', (0, 0.15, 6.9), (0.8, 0.6, 0.85), BRONZE_DARK),           # beard
        ('ell', (0, 1.35, 8.5), (1.05, 1.0, 0.75), BRONZE_DARK),          # hair
        ('box', (-0.8, -0.3, 7.9), (0.8, -0.1, 8.1), BRONZE_DARK),        # glasses
    ]

    def inside(kind, p, lx, ly, lz):
        if kind == 'ell':
            (cx, cy, cz), (rx, ry, rz) = p
            return ((lx - cx) / rx) ** 2 + ((ly - cy) / ry) ** 2 + ((lz - cz) / rz) ** 2 <= 1
        if kind == 'box':
            (x0, y0, z0), (x1, y1, z1) = p
            return ((x0 <= lx) & (lx <= x1) & (y0 <= ly) & (ly <= y1)
                    & (z0 <= lz) & (lz <= z1))
        a, b, r = p
        a, b = np.array(a), np.array(b)
        ab = b - a
        t = np.clip(((lx - a[0]) * ab[0] + (ly - a[1]) * ab[1] + (lz - a[2]) * ab[2])
                    / float(ab @ ab), 0, 1)
        return ((lx - a[0] - t * ab[0]) ** 2 + (ly - a[1] - t * ab[1]) ** 2
                + (lz - a[2] - t * ab[2]) ** 2) <= r * r

    xs = np.arange(ox - 8, ox + 9)
    ys = np.arange(oy - 12, oy + 8)
    zs = np.arange(1, oz + 20)
    LX = ((xs + 0.5 - ox) / S)[:, None, None]
    LY = ((ys + 0.5 - oy) / S)[None, :, None]
    LZ = ((zs + 0.5 - oz) / S)[None, None, :]
    LX, LY, LZ = np.broadcast_arrays(LX, LY, LZ)
    out = np.zeros(LX.shape, dtype=np.uint8)
    for part in parts:
        kind, col = part[0], part[-1]
        out[inside(kind, part[1:-1], LX, LY, LZ)] = col
    region = G[xs[0]:xs[-1] + 1, ys[0]:ys[-1] + 1, zs[0]:zs[-1] + 1]
    region[out > 0] = out[out > 0]
    box(436, 446, FREUD_Y - 1, FREUD_Y, 3, 7, BRONZE_DARK)          # plaque


# --------------------------------------------------------------------------
# Trees
# --------------------------------------------------------------------------
def leaf_blob(cx, cy, cz, rx, ry, rz, colours, r, density=0.5, shell=7):
    """Clumpy, hollow ellipsoid of foliage (only fills empty voxels)."""
    x0, x1 = _clip(cx - rx - 1, cx + rx + 2, NX)
    y0, y1 = _clip(cy - ry - 1, cy + ry + 2, NY)
    z0, z1 = _clip(cz - rz - 1, cz + rz + 2, NZ)
    if x0 >= x1 or y0 >= y1 or z0 >= z1:
        return
    X = (np.arange(x0, x1) + 0.5 - cx)[:, None, None] / rx
    Y = (np.arange(y0, y1) + 0.5 - cy)[None, :, None] / ry
    Z = (np.arange(z0, z1) + 0.5 - cz)[None, None, :] / rz
    d = np.sqrt(X ** 2 + Y ** 2 + Z ** 2)
    inner = max(0.0, 1.0 - shell / min(rx, ry, rz))
    m = (d <= 1.0) & (d >= inner)
    shp = m.shape
    cs = tuple((s + 3) // 4 for s in shp)
    coarse = r.random(cs).repeat(4, 0).repeat(4, 1).repeat(4, 2)[:shp[0], :shp[1], :shp[2]]
    sub = G[x0:x1, y0:y1, z0:z1]
    keep = m & (0.6 * coarse + 0.4 * r.random(shp) < density) & (sub == 0)
    n = int(keep.sum())
    if n == 0:
        return
    pick = (r.random(n) * len(colours)).astype(int)
    sub[keep] = np.asarray(colours, dtype=np.uint8)[pick]


def deciduous(x, y, height, crown, trunk, colours, seed, density=0.5, mulch=3.0):
    """Shade tree: trunk, 4-6 main limbs with side branches, clumpy crown."""
    r = np.random.default_rng(seed)
    zb = height * 0.36
    if mulch:
        disc(x, y, trunk * mulch, 0, 1, MULCH)
    capsule((x, y, 0), (x, y, 7), trunk * 1.7, trunk * 1.1, TRUNK2)        # root flare
    top = np.array([x + r.normal(0, 1.5), y + r.normal(0, 1.5), zb])
    capsule((x, y, 0), top, trunk * 1.15, trunk * 0.8, TRUNK)
    tips = []
    n = int(r.integers(4, 7))
    for i in range(n):
        ang = 2 * math.pi * (i + r.uniform(-0.3, 0.3)) / n
        elev = r.uniform(0.55, 1.0)
        L = crown * r.uniform(0.6, 0.8)
        dv = np.array([math.cos(ang) * math.cos(elev), math.sin(ang) * math.cos(elev), math.sin(elev)])
        start = top - np.array([0.0, 0.0, r.uniform(0, zb * 0.12)])
        end = start + dv * L
        capsule(start, end, trunk * 0.62, trunk * 0.28, TRUNK)
        tips.append((end, crown * r.uniform(0.34, 0.42)))
        for _ in range(2):
            s2 = start + (end - start) * r.uniform(0.45, 0.8)
            a2 = ang + r.uniform(-0.9, 0.9)
            e2 = min(1.25, elev + r.uniform(-0.2, 0.45))
            d2 = np.array([math.cos(a2) * math.cos(e2), math.sin(a2) * math.cos(e2), math.sin(e2)])
            p2 = s2 + d2 * L * r.uniform(0.35, 0.5)
            capsule(s2, p2, trunk * 0.3, 0.9, TRUNK)
            tips.append((p2, crown * r.uniform(0.26, 0.34)))
    for p, rad in tips:
        leaf_blob(p[0], p[1], p[2] + rad * 0.25, rad, rad, rad * 0.8, colours, r, density)
    leaf_blob(top[0], top[1], top[2] + crown * 0.62, crown * 0.5, crown * 0.5, crown * 0.42,
              colours, r, density)


def spruce(x, y, height, base, seed):
    """Conical evergreen with drooping tiers."""
    r = np.random.default_rng(seed)
    disc(x, y, 9, 0, 1, MULCH)
    capsule((x, y, 0), (x, y, height), 2.6, 0.8, TRUNK2)
    zb = 14
    x0, x1 = _clip(x - base - 2, x + base + 3, NX)
    y0, y1 = _clip(y - base - 2, y + base + 3, NY)
    z0, z1 = _clip(zb, height + 6, NZ)
    X = np.arange(x0, x1)[:, None, None] + 0.5 - x
    Y = np.arange(y0, y1)[None, :, None] + 0.5 - y
    Z = np.arange(z0, z1)[None, None, :] + 0.5
    frac = np.clip((Z - zb) / (height + 4 - zb), 0, 1)
    tier = 1.0 - ((Z - zb) % 16) / 16.0
    R = base * (1 - frac) * (0.7 + 0.3 * tier) + 1.5
    d = np.sqrt(X ** 2 + Y ** 2)
    m = (d <= R) & (d >= R - 6)
    shp = m.shape
    cs = tuple((s + 2) // 3 for s in shp)
    coarse = r.random(cs).repeat(3, 0).repeat(3, 1).repeat(3, 2)[:shp[0], :shp[1], :shp[2]]
    sub = G[x0:x1, y0:y1, z0:z1]
    keep = m & (0.6 * coarse + 0.4 * r.random(shp) < 0.7) & (sub == 0)
    n = int(keep.sum())
    sub[keep] = np.where(r.random(n) < 0.6, CONIFER, CONIFER2).astype(np.uint8)


TREES = [
    # (kind, x, y): row of big trees just inside the Main Street fence
    ('maple', 110, 250), ('oak', 300, 245), ('maple', 700, 245), ('oak', 880, 250),
    ('maple', 1240, 250),
    # shade trees on the Green
    ('oak', 420, 420), ('oak', 620, 420), ('maple', 120, 470), ('maple', 330, 530),
    ('maple', 760, 540), ('maple', 1000, 450), ('oak', 1250, 450), ('maple', 850, 380),
    # red Japanese maples beside Red Square, ornamental trees at the UC plaza
    ('red', 345, 605), ('red', 655, 605), ('small', 960, 650), ('small', 1200, 650),
    # evergreens at the building corners
    ('spruce', 140, 720), ('spruce', 140, 830), ('spruce', 1355, 730), ('spruce', 1355, 845),
    # behind the buildings
    ('back', 320, 950), ('back', 680, 955), ('back', 1000, 960), ('back', 1250, 955),
    ('spruce', 100, 960),
    # street trees along Main Street
    ('street', 265, 167), ('street', 765, 167), ('street', 1240, 167),
]


def plant_trees():
    for i, (kind, x, y) in enumerate(TREES):
        seed = 1000 + i
        if kind == 'oak':
            deciduous(x, y, 175, 74, 4.2, (LEAF, LEAF2, LEAF2, LEAF3), seed, 0.5)
        elif kind == 'maple':
            deciduous(x, y, 150, 60, 3.4, (LEAF, LEAF3, LEAF3, LEAF2), seed, 0.5)
        elif kind == 'back':
            deciduous(x, y, 140, 46, 3.2, (LEAF, LEAF2, LEAF3), seed, 0.5)
        elif kind == 'red':
            deciduous(x, y, 62, 26, 1.8, (RED_LEAF, RED_LEAF2), seed, 0.6)
        elif kind == 'small':
            deciduous(x, y, 70, 28, 2.0, (LEAF3, LOCUST), seed, 0.58, mulch=2.6)
        elif kind == 'street':
            deciduous(x, y, 120, 40, 2.6, (LOCUST, LOCUST, LEAF3), seed, 0.42, mulch=2.4)
        else:
            spruce(x, y, 165, 34, seed)


def check_trees():
    """Warn about trees whose crowns clip into buildings or street furniture."""
    found = np.isin(G, TREE_SET + [0], invert=True)
    for kind, x, y in TREES:
        r = 30 if kind in ('red', 'small') else 50
        if found[max(0, x - r):x + r, max(0, y - r):y + r, 45:200].any():
            print('note: crown of %s tree at (%d, %d) is close to a structure' % (kind, x, y))


# --------------------------------------------------------------------------
# Finishing: colour variation
# --------------------------------------------------------------------------
def vary(base, alts, p):
    m = G == base
    r = rng.random(int(m.sum()))
    vals = np.full(r.shape, base, dtype=np.uint8)
    acc = 0.0
    for alt, pa in zip(alts, p):
        vals[(r >= acc) & (r < acc + pa)] = alt
        acc += pa
    G[m] = vals


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def write_vox(path, data):
    sx, sy, sz = data.shape
    xs, ys, zs = np.nonzero(data)
    n = len(xs)
    xyzi = np.empty((n, 4), dtype=np.uint8)
    xyzi[:, 0], xyzi[:, 1], xyzi[:, 2] = xs, ys, zs
    xyzi[:, 3] = data[xs, ys, zs]
    rgba = bytearray(256 * 4)
    for i in range(1, 256):
        r, g, b = PALETTE.get(i, (128, 128, 128))
        rgba[(i - 1) * 4:(i - 1) * 4 + 4] = bytes((r, g, b, 255))

    def chunk(cid, content):
        return cid + struct.pack('<ii', len(content), 0) + content

    size = chunk(b'SIZE', struct.pack('<iii', sx, sy, sz))
    xyz = chunk(b'XYZI', struct.pack('<i', n) + xyzi.tobytes())
    pal = chunk(b'RGBA', bytes(rgba))
    children = size + xyz + pal
    with open(path, 'wb') as f:
        f.write(b'VOX ' + struct.pack('<i', 150))
        f.write(b'MAIN' + struct.pack('<ii', 0, len(children)) + children)
    return n


def to_td(x, y, z):
    """Grid voxel coordinate -> Teardown metres, map centre at origin."""
    return ((x - NX / 2) * VOX, z * VOX, -(y - NY / 2) * VOX)


def export(out):
    vox_dir = os.path.join(out, 'vox')
    if os.path.isdir(vox_dir):
        shutil.rmtree(vox_dir)
    os.makedirs(vox_dir)
    lines = []
    total = 0
    for cx in range(0, NX, CHUNK):
        for cy in range(0, NY, CHUNK):
            for cz in range(0, NZ, CHUNK):
                sub = G[cx:cx + CHUNK, cy:cy + CHUNK, cz:cz + CHUNK]
                if not sub.any():
                    continue
                name = 'c_%d_%d_%d.vox' % (cx // CHUNK, cy // CHUNK, cz // CHUNK)
                total += write_vox(os.path.join(vox_dir, name), sub)
                # Teardown places a vox by the centre of its bottom face
                tx, ty, tz = to_td(cx + CHUNK / 2, cy + CHUNK / 2, cz)
                lines.append('\t\t<vox pos="%.1f %.1f %.1f" file="MOD/vox/%s"/>' % (tx, ty, tz, name))

    # Ground: dirt on top of hard masonry, larger than the map so a small
    # pivot difference can never leave a gap.  Voxbox tiles are <= 256.
    margin, tile = 150, 256
    gx0, gx1 = -NX // 2 - margin, NX // 2 + margin
    gz0, gz1 = -NY // 2 - margin, NY // 2 + margin
    ground_lines = []
    for x in range(gx0, gx1, tile):
        for z in range(gz0, gz1, tile):
            w, d = min(tile, gx1 - x), min(tile, gz1 - z)
            p = (x * VOX, z * VOX)
            ground_lines.append('\t\t<voxbox pos="%.1f -0.1 %.1f" size="%d 1 %d" color="0.33 0.45 0.22" material="dirt"/>' % (p[0], p[1], w, d))
            ground_lines.append('\t\t<voxbox pos="%.1f -0.5 %.1f" size="%d 4 %d" color="0.40 0.31 0.22" material="dirt"/>' % (p[0], p[1], w, d))
            ground_lines.append('\t\t<voxbox pos="%.1f -0.8 %.1f" size="%d 3 %d" color="0.35 0.34 0.33" material="hardmasonry"/>' % (p[0], p[1], w, d))

    sx, sy, sz = to_td(500, 170, 3)        # on the sidewalk outside the main gate
    xml = '\n'.join([
        '<scene version="6" shadowVolume="160 50 120">',
        '\t<environment template="sunny"/>',
        '\t<spawnpoint pos="%.1f %.1f %.1f" rot="0 0 0"/>' % (sx, sy, sz),
        '\t<group name="ground">',
        *ground_lines,
        '\t</group>',
        '\t<group name="clark_university">',
        *lines,
        '\t</group>',
        '</scene>',
        '',
    ])
    with open(os.path.join(out, 'main.xml'), 'w') as f:
        f.write(xml)
    with open(os.path.join(out, 'info.txt'), 'w') as f:
        f.write('name = Clark University\n'
                'author = stevehahahahah\n'
                'description = Clark University, Worcester MA: Main Street and the "C" gate, '
                'the Green with its trees, Jonas Clark Hall (1887) and the Higgins University '
                'Center with furnished interiors, Red Square and the seated Sigmund Freud '
                'statue. Everything is destructible.\n'
                'tags = Map\n')
    return len(lines), total


def render_preview(path, width=1600, grid=None):
    """Isometric-ish preview seen from the south-east (of `grid`, default: whole map)."""
    G = globals()['G'] if grid is None else grid
    NX = G.shape[0]
    solid = G > 0
    exposed = np.zeros_like(solid)
    exposed[:, :, -1] |= solid[:, :, -1]
    exposed[:, :, :-1] |= solid[:, :, :-1] & ~solid[:, :, 1:]       # top
    exposed[:, 1:, :] |= solid[:, 1:, :] & ~solid[:, :-1, :]         # south
    exposed[:-1, :, :] |= solid[:-1, :, :] & ~solid[1:, :, :]        # east
    exposed[:, 0, :] |= solid[:, 0, :]
    exposed[-1, :, :] |= solid[-1, :, :]
    top = np.zeros_like(solid)
    top[:, :, :-1] = solid[:, :, :-1] & ~solid[:, :, 1:]
    top[:, :, -1] = solid[:, :, -1]
    xs, ys, zs = np.nonzero(exposed)
    del exposed
    cols = G[xs, ys, zs]
    is_top = top[xs, ys, zs]
    del top, solid
    east = np.zeros(len(xs), dtype=bool)
    m = xs < NX - 1
    east[m] = G[xs[m] + 1, ys[m], zs[m]] == 0
    yaw, el = math.radians(-30), math.radians(35)
    cw, sw = math.cos(yaw), math.sin(yaw)
    u = xs * cw - ys * sw
    depth_h = xs * sw + ys * cw                   # further north = further away
    v = zs * math.cos(el) + depth_h * math.sin(el)
    near = -depth_h * math.cos(el) + zs * math.sin(el)
    sc = width / (u.max() - u.min() + 20)
    px = ((u - u.min() + 10) * sc).astype(np.int32)
    py = ((v.max() - v + 10) * sc).astype(np.int32)
    H = int(py.max() + 12)
    pal = np.zeros((256, 3), dtype=np.float32)
    for i, c in PALETTE.items():
        pal[i] = c
    shade = np.where(is_top, 1.0, np.where(east, 0.72, 0.86)).astype(np.float32)
    rgb = pal[cols] * shade[:, None]
    order = np.argsort(near)
    img = np.zeros((H, width, 3), dtype=np.float32)
    img[:] = (170, 200, 230)
    zbuf = np.full((H, width), -1e9, dtype=np.float32)
    s = max(1, int(math.ceil(sc)) + 1)
    for dx in range(s):
        for dy in range(s):
            X = np.clip(px + dx, 0, width - 1)
            Y = np.clip(py + dy, 0, H - 1)
            flat = Y[order] * width + X[order]
            # last occurrence in ascending-near order = nearest voxel
            uniq_rev, idx = np.unique(flat[::-1], return_index=True)
            sel = order[::-1][idx]
            cur = zbuf.ravel()[uniq_rev]
            better = near[sel] > cur
            zbuf.ravel()[uniq_rev[better]] = near[sel][better]
            img.reshape(-1, 3)[uniq_rev[better]] = rgb[sel][better]
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(path, quality=90)


def build():
    ground()
    main_street()
    campus_fence()
    jonas_clark_hall()
    jch_structure()
    furnish_jch()
    university_center()
    uc_structure()
    furnish_uc()
    landscape()
    freud_statue()
    plant_trees()
    check_trees()
    vary(BRICK, (BRICK2, BRICK3), (0.2, 0.1))
    vary(UC_BRICK, (UC_BRICK2,), (0.25,))
    vary(GRASS, (GRASS2, GRASS3), (0.3, 0.2))
    vary(SLATE, (SLATE2,), (0.3,))
    vary(ROOF_METAL, (ROOF_METAL2,), (0.3,))
    vary(ASPHALT, (ASPHALT2,), (0.3,))


VIEWS = {
    # name: (x range, y range, z range) of the grid to render
    'main_gate': ((420, 580), (100, 260), (0, 90)),
    'jonas_clark_entrance': ((430, 570), (600, 700), (0, 256)),
    'freud_statue': ((395, 460), (540, 600), (0, 40)),
    'university_center': ((840, 1320), (560, 900), (0, 256)),
    'jch_first_floor': ((196, 804), (JY0 + 3, 864), (0, JL[2] - 2)),
    'jch_second_floor': ((196, 804), (JY0 + 3, 864), (0, JL[3] - 2)),
    'uc_ground_floor': ((856, 1304), (668, 884), (0, UL[1] - 2)),
    'uc_tilton_hall': ((856, 1304), (668, 884), (0, UL[2] - 2)),
}


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, 'ClarkUniversity')
    os.makedirs(out, exist_ok=True)
    build()
    n_chunks, n_vox = export(out)
    render_preview(os.path.join(out, 'preview.jpg'))
    docs = os.path.join(root, 'docs')
    os.makedirs(docs, exist_ok=True)
    for name, ((x0, x1), (y0, y1), (z0, z1)) in VIEWS.items():
        render_preview(os.path.join(docs, name + '.jpg'), 1200,
                       np.ascontiguousarray(G[x0:x1, y0:y1, z0:z1]))
    print('wrote %d chunks, %d voxels -> %s' % (n_chunks, n_vox, out))


if __name__ == '__main__':
    main()
