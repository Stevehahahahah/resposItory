#!/usr/bin/env python3
"""Generate a Teardown map of Clark University (Worcester, MA).

Scope: Jonas Clark Hall, Higgins University Center, the Green / Red Square
between them, and the seated Sigmund Freud statue.

The whole scene is built in one voxel grid (1 voxel = 0.1 m, Teardown scale)
and exported as equally sized 128^3 MagicaVoxel chunks plus a main.xml.

Grid axes: x = east, y = north, z = up.  Teardown axes: (x, z, -y).

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
GRANITE, GRANITE_DARK, GRANITE_TEXT, SLATE, SLATE2 = 41, 42, 43, 44, 45
TRUNK, DOOR_WOOD, BENCH_WOOD, FLOOR_WOOD = 57, 58, 59, 60
CONCRETE, CONCRETE2, CONCRETE_LIGHT = 73, 74, 75
BRICK, BRICK2, BRICK3, UC_BRICK, UC_BRICK2, PAVER, PAVER2 = 89, 90, 91, 92, 93, 94, 95
PLASTER, TRIM = 105, 106
METAL_DARK, METAL_GRAY = 121, 122
BRONZE, BRONZE_DARK, BRONZE_LIGHT = 137, 138, 139
LAMP = 153
LEAF, LEAF2, LEAF3 = 225, 226, 227

PALETTE = {
    GLASS: (120, 150, 170), GLASS_DARK: (70, 90, 110),
    GRASS: (88, 134, 58), GRASS2: (78, 122, 50), GRASS3: (100, 146, 66),
    DIRT: (101, 78, 56), MULCH: (82, 55, 38),
    GRANITE: (182, 178, 170), GRANITE_DARK: (140, 136, 130), GRANITE_TEXT: (70, 68, 66),
    SLATE: (62, 66, 72), SLATE2: (72, 76, 82),
    TRUNK: (88, 66, 48), DOOR_WOOD: (92, 52, 30), BENCH_WOOD: (130, 92, 58),
    FLOOR_WOOD: (150, 112, 74),
    CONCRETE: (176, 172, 164), CONCRETE2: (160, 156, 150), CONCRETE_LIGHT: (204, 200, 190),
    BRICK: (148, 62, 44), BRICK2: (132, 54, 40), BRICK3: (160, 74, 52),
    UC_BRICK: (128, 70, 52), UC_BRICK2: (116, 62, 48),
    PAVER: (150, 58, 46), PAVER2: (124, 48, 40),
    PLASTER: (226, 222, 210), TRIM: (236, 232, 220),
    METAL_DARK: (40, 42, 44), METAL_GRAY: (110, 114, 118),
    BRONZE: (92, 70, 42), BRONZE_DARK: (62, 46, 30), BRONZE_LIGHT: (128, 100, 62),
    LAMP: (245, 240, 220),
    LEAF: (62, 104, 40), LEAF2: (52, 90, 34), LEAF3: (76, 118, 46),
}

VOX = 0.1          # metres per voxel
CHUNK = 128
NX, NY, NZ = 1024, 896, 256
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


def disc(cx, cy, r, z0, z1, c):
    x0, x1 = _clip(cx - r - 1, cx + r + 2, NX)
    y0, y1 = _clip(cy - r - 1, cy + r + 2, NY)
    xs = (np.arange(x0, x1) + 0.5 - cx)[:, None]
    ys = (np.arange(y0, y1) + 0.5 - cy)[None, :]
    m = xs ** 2 + ys ** 2 <= r * r
    for z in range(z0, z1):
        G[x0:x1, y0:y1, z][m] = c


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
# Generic interior pieces
# --------------------------------------------------------------------------
def stair_x(x0, y0, y1, z_base, z_top, run=3):
    """Solid stair climbing toward +x from floor z_base to floor z_top."""
    rise = z_top - z_base
    steps = int(math.ceil(rise / 2.0))
    for i in range(steps):
        top = z_base + int(round((i + 1) * rise / steps))
        box(x0 + i * run, x0 + (i + 1) * run, y0, y1, z_base, top, CONCRETE2)
    return x0 + steps * run


def floor_slab(x0, x1, y0, y1, z, wood=True):
    box(x0, x1, y0, y1, z - 2, z, CONCRETE)
    if wood:
        box(x0, x1, y0, y1, z - 1, z, FLOOR_WOOD)


def interior_wall_x(x0, x1, y, z0, z1, doors, door_w=12, door_h=22):
    """Plaster wall along x at y..y+2 with door openings centred at `doors`."""
    box(x0, x1, y, y + 2, z0, z1, PLASTER)
    for dx in doors:
        box(dx - door_w // 2, dx + door_w // 2, y, y + 2, z0, z0 + door_h, 0)


# --------------------------------------------------------------------------
# Jonas Clark Hall (north side, main facade faces south / -y)
# --------------------------------------------------------------------------
JX0, JX1, JY0, JY1 = 200, 800, 680, 860
J_LEVELS = [1, 16, 61, 106, 151]            # floor surface heights (z)
BAY_X0, BAY_X1, BAY_Y0 = 445, 555, 672      # projecting central bay


def jonas_clark_hall():
    T = 3
    # ground slab + walls
    box(JX0, JX1, JY0, JY1, 0, 1, CONCRETE)
    shell(JX0, JX1, JY0, JY1, 1, 16, GRANITE, T)          # raised granite basement
    shell(JX0, JX1, JY0, JY1, 16, 151, BRICK, T)
    # corner pilasters (slightly proud of the wall)
    for x0 in (JX0 - 2, JX1 - 10):
        box(x0, x0 + 12, JY0 - 2, JY0 + 4, 1, 151, BRICK)
        box(x0, x0 + 12, JY1 - 4, JY1 + 2, 1, 151, BRICK)
        box(x0, x0 + 12, JY0 - 2, JY0 + 4, 1, 16, GRANITE)
        box(x0, x0 + 12, JY1 - 4, JY1 + 2, 1, 16, GRANITE)
    # central bay: solid thick brick block in front of the facade
    box(BAY_X0, BAY_X1, BAY_Y0, JY0 + T, 1, 151, BRICK)
    box(BAY_X0, BAY_X1, BAY_Y0, JY0 + T, 1, 16, GRANITE)

    # belt courses at the floor lines (granite, 1 voxel proud)
    for z in (14, 59, 104):
        box(JX0 - 1, JX1 + 1, JY0 - 1, JY0, z, z + 3, GRANITE)
        box(JX0 - 1, JX1 + 1, JY1, JY1 + 1, z, z + 3, GRANITE)
        box(JX0 - 1, JX0, JY0, JY1, z, z + 3, GRANITE)
        box(JX1, JX1 + 1, JY0, JY1, z, z + 3, GRANITE)
        box(BAY_X0 - 1, BAY_X1 + 1, BAY_Y0 - 1, BAY_Y0, z, z + 3, GRANITE)

    # ---- windows -------------------------------------------------------
    west = list(range(JX0 + 25, BAY_X0 - 25, 30))          # 225 .. 405
    front_cols = west + [1000 - c for c in west]
    back_cols = front_cols + [470, 500, 530]
    side_rows = list(range(JY0 + 40, JY1 - 25, 45))

    def floor_windows(axis, centres, d0, d1, gd, outside_d):
        for c in centres:
            a0, a1 = c - 7, c + 7
            opening(axis, a0, a1, 4, 12, d0, d1, gd)                       # basement
            for zb in (24, 69):                                            # floors 1-2
                opening(axis, a0, a1, zb, zb + 28, d0, d1, gd)
                # granite lintel + sill on the outside face
                if axis == 'x':
                    box(a0 - 2, a1 + 2, outside_d, outside_d + 1, zb + 28, zb + 31, GRANITE)
                    box(a0 - 1, a1 + 1, outside_d, outside_d + 1, zb - 2, zb, GRANITE)
                else:
                    box(outside_d, outside_d + 1, a0 - 2, a1 + 2, zb + 28, zb + 31, GRANITE)
                    box(outside_d, outside_d + 1, a0 - 1, a1 + 1, zb - 2, zb, GRANITE)
            # floor 3: Romanesque round-arched windows
            if axis == 'x':
                arch_ring('x', a0, a1, 134, outside_d, outside_d + 1, BRICK2)
            else:
                arch_ring('y', a0, a1, 134, outside_d, outside_d + 1, BRICK2)
            opening(axis, a0, a1, 114, 134, d0, d1, gd, arch=True)

    floor_windows('x', front_cols, JY0, JY0 + T, JY0 + 1, JY0 - 1)
    floor_windows('x', back_cols, JY1 - T, JY1, JY1 - 2, JY1)
    floor_windows('y', side_rows, JX0, JX0 + T, JX0 + 1, JX0 - 1)
    floor_windows('y', side_rows, JX1 - T, JX1, JX1 - 2, JX1)

    # ---- central bay: entrance, granite name blocks, arched triple window --
    # granite steps up to the first floor (z=16)
    for i in range(8):
        box(470 - 4, 530 + 4, BAY_Y0 - 4 * (8 - i), BAY_Y0, 1, 2 * (i + 1), GRANITE)
    # arched doorway through the bay with glass fanlight
    opening('x', 485, 515, 16, 42, BAY_Y0, JY0 + T)
    arch_ring('x', 485, 515, 42, BAY_Y0 - 1, BAY_Y0, GRANITE, thick=3)
    opening('x', 485, 515, 42, 43, BAY_Y0, JY0 + T, BAY_Y0 + 4, arch=True)
    box(485, 515, BAY_Y0, JY0 + T, 42, 43, DOOR_WOOD)            # transom bar
    # side lights next to the door
    for c in (466, 534):
        opening('x', c - 5, c + 5, 22, 50, BAY_Y0, JY0 + T, BAY_Y0 + 4)
    # three stacked granite blocks: CLARK / UNIVERSITY / 1887
    for (word, z0) in (("1887", 64), ("UNIVERSITY", 76), ("CLARK", 88)):
        box(464, 537, BAY_Y0 - 2, BAY_Y0, z0, z0 + 11, GRANITE)
        draw_text(word, 500, z0 + 8, BAY_Y0 - 2, GRANITE_TEXT)
    # floor 3 arched triple window
    for c in (470, 500, 530):
        arch_ring('x', c - 7, c + 7, 134, BAY_Y0 - 1, BAY_Y0, BRICK2)
        opening('x', c - 7, c + 7, 114, 134, BAY_Y0, JY0 + T, BAY_Y0 + 4, arch=True)

    # ---- cornice -------------------------------------------------------
    for k, (z0, z1) in enumerate(((151, 154), (154, 157), (157, 161))):
        p = k + 1
        box(JX0 - 2 - p, JX1 + 2 + p, JY0 - 2 - p, JY1 + 2 + p, z0, z1, TRIM)
        box(BAY_X0 - p, BAY_X1 + p, BAY_Y0 - p, JY0, z0, z1, TRIM)
    for x in range(JX0, JX1, 5):                                   # dentils
        box(x, x + 2, JY0 - 4, JY0, 148, 151, TRIM)
        box(x, x + 2, JY1, JY1 + 4, 148, 151, TRIM)
    box(JX0 + 3, JX1 - 3, JY0 + 3, JY1 - 3, 153, 161, 0)           # hollow attic
    box(JX0 + 3, JX1 - 3, JY0 + 3, JY1 - 3, 151, 153, CONCRETE)    # attic floor

    # ---- slate hipped roof (hollow shell) ------------------------------
    rx0, rx1, ry0, ry1 = JX0 - 4, JX1 + 4, JY0 - 4, JY1 + 4
    k = 0
    while True:
        a0, a1, b0, b1 = rx0 + 2 * k, rx1 - 2 * k, ry0 + 2 * k, ry1 - 2 * k
        if b1 - b0 <= 2:
            break
        z = 161 + k
        box(a0, a1, b0, b1, z, z + 1, SLATE)
        if b1 - b0 > 12:
            box(a0 + 6, a1 - 6, b0 + 6, b1 - 6, z, z + 1, 0)
        k += 1
    # central pavilion above the cornice: brick parapet with a round lunette
    # (where the clock tower stood until the 1924 storm)
    box(BAY_X0, BAY_X1, BAY_Y0, BAY_Y0 + 20, 161, 192, BRICK)
    box(BAY_X0 - 2, BAY_X1 + 2, BAY_Y0 - 2, BAY_Y0 + 22, 192, 196, TRIM)
    arch_ring('x', 486, 514, 172, BAY_Y0 - 1, BAY_Y0, GRANITE, thick=2)
    opening('x', 486, 514, 166, 172, BAY_Y0, BAY_Y0 + 6, BAY_Y0 + 3, arch=True)
    for x in (BAY_X0, BAY_X1 - 6):                                # little piers
        box(x, x + 6, BAY_Y0 - 1, BAY_Y0 + 21, 161, 192, BRICK3)
    # chimneys
    for x in (290, 710):
        box(x, x + 12, 790, 802, 175, 215, BRICK)
        box(x - 1, x + 13, 789, 803, 215, 218, GRANITE)

    # ---- interior ------------------------------------------------------
    ix0, ix1, iy0, iy1 = JX0 + T, JX1 - T, JY0 + T, JY1 - T
    for z in J_LEVELS[1:4]:
        floor_slab(ix0, ix1, iy0, iy1, z)
    doors = list(range(ix0 + 40, ix1 - 20, 60))
    for zb, zt in zip(J_LEVELS[:4], J_LEVELS[1:5]):
        top = zt - 2
        interior_wall_x(ix0, ix1, 755, zb, top, doors)
        interior_wall_x(ix0, ix1, 785, zb, top, doors)
        for x in range(ix0 + 90, ix1 - 30, 90):                    # room walls
            if 440 <= x <= 560:
                continue
            box(x, x + 2, iy0, 755, zb, top, PLASTER)
            box(x, x + 2, 787, iy1, zb, top, PLASTER)
        # open lobby / stair hall in the middle
        box(445, 555, 755, 787, zb, top, 0)
        box(445, 555, 787, iy1, zb, top, 0)
        box(445, 555, iy0, 755, J_LEVELS[1], J_LEVELS[2] - 2, 0)    # entrance hall
    # stairs, alternating lanes so they never overlap
    lane_a, lane_b = (800, 820), (830, 850)
    lanes = [lane_b, lane_a, lane_b]
    for (zb, zt), lane in zip(zip(J_LEVELS[:3], J_LEVELS[1:4]), lanes):
        end = stair_x(460, lane[0], lane[1], zb, zt)
        box(455, end + 4, lane[0] - 1, lane[1] + 1, zt - 2, zt, 0)   # hole above


# --------------------------------------------------------------------------
# Higgins University Center (south side, main facade faces north / +y)
# --------------------------------------------------------------------------
UX0, UX1, UY0, UY1 = 250, 750, 80, 300
U_LEVELS = [1, 41, 81, 121, 161]
ATX0, ATX1, ATY1 = 440, 560, 330            # glass atrium


def university_center():
    T = 3
    box(UX0, UX1, UY0, UY1, 0, 1, CONCRETE)
    shell(UX0, UX1, UY0, UY1, 1, 170, UC_BRICK, T)
    box(UX0 - 1, UX1 + 1, UY0 - 1, UY1 + 1, 170, 173, CONCRETE_LIGHT)   # parapet cap

    # ribbon windows between brick piers
    def ribbons(axis, a_start, a_end, d0, d1, gd):
        for i, zb in enumerate(U_LEVELS[:4]):
            z0, z1 = (zb + 6, zb + 32) if i == 0 else (zb + 10, zb + 32)
            a = a_start + 12
            while a + 40 <= a_end - 8:
                opening(axis, a, a + 40, z0, z1, d0, d1, gd)
                for m in range(a + 10, a + 40, 10):                   # mullions
                    if axis == 'x':
                        box(m, m + 1, gd, gd + 1, z0, z1, METAL_DARK)
                    else:
                        box(gd, gd + 1, m, m + 1, z0, z1, METAL_DARK)
                a += 50

    ribbons('x', UX0, ATX0 - 10, UY1 - T, UY1, UY1 - 2)
    ribbons('x', ATX1 + 10, UX1, UY1 - T, UY1, UY1 - 2)
    ribbons('x', UX0, UX1, UY0, UY0 + T, UY0 + 1)
    ribbons('y', UY0, UY1, UX0, UX0 + T, UX0 + 1)
    ribbons('y', UY0, UY1, UX1 - T, UX1, UX1 - 2)

    # concrete floor bands, 1 voxel proud, all the way round
    for z in U_LEVELS[1:]:
        box(UX0 - 1, UX1 + 1, UY0 - 1, UY1 + 1, z - 3, z + 1, CONCRETE_LIGHT)
        box(UX0 + T, UX1 - T, UY0 + T, UY1 - T, z - 3, z + 1, 0)

    # ---- glass atrium (full height entrance facing the Green) ---------
    box(ATX0, ATX1, UY1 - T, ATY1, 1, 126, GLASS)
    box(ATX0 + 2, ATX1 - 2, UY1 - T, ATY1 - 2, 1, 126, 0)            # hollow
    for x in range(ATX0, ATX1 + 1, 20):                               # mullions
        box(x - 1, x + 1, UY1, ATY1, 1, 126, METAL_DARK)
    for x0, x1 in ((ATX0, ATX0 + 2), (ATX1 - 2, ATX1)):
        for y in range(UY1, ATY1 + 1, 15):
            box(x0, x1, y - 1, y + 1, 1, 126, METAL_DARK)
    for z in range(1, 127, 25):                                       # transoms
        box(ATX0, ATX1, ATY1 - 2, ATY1, z, z + 2, METAL_DARK)
        box(ATX0, ATX0 + 2, UY1, ATY1, z, z + 2, METAL_DARK)
        box(ATX1 - 2, ATX1, UY1, ATY1, z, z + 2, METAL_DARK)
    box(ATX0 - 2, ATX1 + 2, UY1 - T, ATY1 + 2, 126, 136, CONCRETE_LIGHT)   # fascia/roof
    draw_text("UNIVERSITY CENTER", 500, 134, ATY1 + 2, METAL_DARK, reading_dir=-1)
    box(480, 520, ATY1 - 2, ATY1, 1, 26, 0)                           # doors (open)
    box(479, 481, ATY1 - 2, ATY1, 1, 27, METAL_DARK)
    box(519, 521, ATY1 - 2, ATY1, 1, 27, METAL_DARK)
    box(479, 521, ATY1 - 2, ATY1, 26, 28, METAL_DARK)
    # lobby opening from the atrium into the building
    box(ATX0 + 2, ATX1 - 2, UY1 - T, UY1, 1, 38, 0)

    # flat roof + rooftop mechanical box
    box(UX0 + T, UX1 - T, UY0 + T, UY1 - T, 161, 164, CONCRETE)
    box(560, 640, 130, 200, 164, 190, METAL_GRAY)
    for x in range(562, 640, 6):
        box(x, x + 2, 129, 130, 168, 186, METAL_DARK)

    # ---- interior ------------------------------------------------------
    ix0, ix1, iy0, iy1 = UX0 + T, UX1 - T, UY0 + T, UY1 - T
    for z in U_LEVELS[1:4]:
        floor_slab(ix0, ix1, iy0, iy1, z, wood=False)
    doors = list(range(370, ix1 - 20, 60))
    for zb, zt in zip(U_LEVELS[:4], U_LEVELS[1:5]):
        top = zt - 2
        interior_wall_x(340, ix1, 180, zb, top, doors)
        interior_wall_x(340, ix1, 210, zb, top, doors)
        for x in range(430, ix1 - 30, 100):
            box(x, x + 2, iy0, 180, zb, top, PLASTER)
        box(340, 342, iy0, iy1, zb, top, PLASTER)                       # stairwell wall
        box(340, 342, 150, 175, zb, zb + 22, 0)                         # its door
        box(340, 342, 215, 260, zb, zb + 22, 0)
    # ground floor: open dining hall behind the atrium
    box(ATX0 - 60, ATX1 + 60, 211, iy1, U_LEVELS[0], U_LEVELS[1] - 2, 0)
    lane_a, lane_b = (100, 120), (125, 145)
    lanes = [lane_a, lane_b, lane_a]
    for (zb, zt), lane in zip(zip(U_LEVELS[:3], U_LEVELS[1:4]), lanes):
        end = stair_x(262, lane[0], lane[1], zb, zt)
        box(258, end + 4, lane[0] - 1, lane[1] + 1, zt - 2, zt, 0)


# --------------------------------------------------------------------------
# Landscape: the Green, Red Square, paths, trees, lamps, benches
# --------------------------------------------------------------------------
GREEN_Y0, GREEN_Y1 = 330, 560
RS_X0, RS_X1, RS_Y0 = 360, 640, 560


def ground():
    G[:, :, 0] = GRASS
    # sidewalk along Jonas Clark Hall and around the University Center
    box(160, 840, 630, JY0, 0, 1, CONCRETE)
    box(JX0 - 20, JX0, JY0, JY1 + 20, 0, 1, CONCRETE)
    box(JX1, JX1 + 20, JY0, JY1 + 20, 0, 1, CONCRETE)
    box(UX0 - 20, UX1 + 20, UY0 - 20, UY1 + 30, 0, 1, CONCRETE)
    box(ATX0 - 40, ATX1 + 40, UY1, ATY1 + 20, 0, 1, CONCRETE2)
    # perimeter walk around the Green
    box(100, 900, GREEN_Y0 - 10, GREEN_Y0, 0, 1, CONCRETE)
    box(100, 110, GREEN_Y0, 640, 0, 1, CONCRETE)
    box(890, 900, GREEN_Y0, 640, 0, 1, CONCRETE)
    # main north-south walk University Center -> Jonas Clark Hall
    box(488, 512, ATY1, RS_Y0, 0, 1, CONCRETE)
    # diagonal paths crossing the Green
    thick_line(110, GREEN_Y0, 500, 445, 14, 0, CONCRETE)
    thick_line(890, GREEN_Y0, 500, 445, 14, 0, CONCRETE)
    thick_line(110, 600, 500, 445, 14, 0, CONCRETE)
    thick_line(890, 600, 500, 445, 14, 0, CONCRETE)
    disc(500, 445, 34, 0, 1, CONCRETE)
    disc(500, 445, 20, 0, 1, GRASS)
    # Red Square: red brick pavers in a basket-weave pattern
    for x, y0, y1 in [(x, RS_Y0, 640) for x in range(RS_X0, RS_X1)] + \
                     [(x, 640, JY0) for x in range(440, 560)]:
        for y in range(y0, y1):
            G[x, y, 0] = PAVER if ((x // 4) + (y // 2) + (x // 8)) % 3 else PAVER2


def tree(cx, cy, r=24, h=52):
    disc(cx, cy, 9, 0, 1, MULCH)
    disc(cx, cy, 2.5, 1, h, TRUNK)
    # a few branches
    for ang in (0.4, 2.3, 4.2):
        for t in range(14):
            x = int(cx + math.cos(ang) * t * 0.9)
            y = int(cy + math.sin(ang) * t * 0.9)
            z = int(h - 16 + t)
            box(x, x + 2, y, y + 2, z, z + 2, TRUNK)
    blobs = [(0, 0, h + 12, r), (r * 0.45, 3, h + 6, r * 0.75),
             (-r * 0.4, -4, h + 8, r * 0.7), (2, r * 0.4, h + 18, r * 0.65)]
    for bx, by, bz, br in blobs:
        sl, m = sphere_mask(cx + bx, cy + by, bz, br, br, br * 0.8)
        m = m & (rng.random(m.shape) > 0.12)
        sub = G[sl]
        sub[m & (sub == 0)] = LEAF


def lamp(x, y):
    box(x, x + 2, y, y + 2, 1, 38, METAL_DARK)
    box(x - 1, x + 3, y - 1, y + 3, 1, 3, METAL_DARK)
    box(x - 1, x + 3, y - 1, y + 3, 38, 43, LAMP)
    box(x - 2, x + 4, y - 2, y + 4, 43, 44, METAL_DARK)


def bench(x0, y0, along='y', length=16):
    """Bench whose seat runs along `along`; backrest on the high side."""
    if along == 'y':
        for y in (y0 + 1, y0 + length - 3):
            box(x0, x0 + 5, y, y + 2, 1, 5, METAL_DARK)
        box(x0, x0 + 5, y0, y0 + length, 5, 6, BENCH_WOOD)
        box(x0 + 4, x0 + 5, y0, y0 + length, 6, 10, BENCH_WOOD)
    else:
        for x in (x0 + 1, x0 + length - 3):
            box(x, x + 2, y0, y0 + 5, 1, 5, METAL_DARK)
        box(x0, x0 + length, y0, y0 + 5, 5, 6, BENCH_WOOD)
        box(x0, x0 + length, y0 + 4, y0 + 5, 6, 10, BENCH_WOOD)


def landscape():
    for (x, y) in [(170, 390), (170, 500), (830, 390), (830, 500),
                   (300, 360), (700, 360), (370, 452), (630, 452),
                   (250, 600), (750, 600), (130, 760), (870, 760),
                   (140, 200), (860, 200)]:
        tree(x, y, r=int(rng.integers(20, 28)), h=int(rng.integers(46, 58)))
    for y in (370, 520):
        lamp(476, y)
        lamp(522, y)
    for x in (380, 620):
        lamp(x, 600)
    for x in (300, 700):
        lamp(x, 640)
    bench(470, 395, 'y')
    bench(525, 395, 'y')
    bench(470, 480, 'y')
    bench(525, 480, 'y')
    bench(410, 590, 'x', 18)
    bench(572, 590, 'x', 18)


# --------------------------------------------------------------------------
# Sigmund Freud statue: bronze Freud seated on a low granite wall, reading
# --------------------------------------------------------------------------
FREUD_X, FREUD_Y, WALL_Y1 = 425, 560, 568


def freud_statue():
    S = 1.8                     # statue is slightly larger than life
    seat_z = 10                 # wall top
    # low granite walls flanking the main walk at the Red Square edge
    for x0, x1 in ((370, 482), (518, 630)):
        box(x0, x1, FREUD_Y, WALL_Y1, 1, seat_z - 1, GRANITE)
        box(x0 - 1, x1 + 1, FREUD_Y - 1, WALL_Y1 + 1, seat_z - 1, seat_z, GRANITE_DARK)
        box(x0, x1, WALL_Y1 + 1, WALL_Y1 + 8, 1, 2, DIRT)
        box(x0 + 2, x1 - 2, WALL_Y1 + 1, WALL_Y1 + 7, 2, 8, LEAF2)   # low hedge

    ox, oy, oz = FREUD_X, FREUD_Y, seat_z
    # (kind, params, colour) in local units (≈ 0.1 m at life size)
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
        p = part[1:-1]
        out[inside(kind, p, LX, LY, LZ)] = col
    region = G[xs[0]:xs[-1] + 1, ys[0]:ys[-1] + 1, zs[0]:zs[-1] + 1]
    region[out > 0] = out[out > 0]
    # small bronze plaque on the wall face
    box(436, 446, FREUD_Y - 1, FREUD_Y, 3, 7, BRONZE_DARK)


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

    sx, sy, sz = to_td(500, 515, 2)
    xml = '\n'.join([
        '<scene version="6" shadowVolume="140 50 140">',
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
                'description = Clark University, Worcester MA: Jonas Clark Hall (1887), '
                'the Higgins University Center, the Green, Red Square and the seated '
                'Sigmund Freud statue. Everything is destructible.\n'
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
    jonas_clark_hall()
    university_center()
    landscape()
    freud_statue()
    vary(BRICK, (BRICK2, BRICK3), (0.2, 0.1))
    vary(UC_BRICK, (UC_BRICK2,), (0.25,))
    vary(GRASS, (GRASS2, GRASS3), (0.3, 0.2))
    vary(SLATE, (SLATE2,), (0.3,))
    vary(LEAF, (LEAF2, LEAF3), (0.3, 0.25))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, 'ClarkUniversity')
    os.makedirs(out, exist_ok=True)
    build()
    n_chunks, n_vox = export(out)
    render_preview(os.path.join(out, 'preview.jpg'))
    docs = os.path.join(root, 'docs')
    os.makedirs(docs, exist_ok=True)
    render_preview(os.path.join(docs, 'view_from_north.jpg'), 1600,
                   np.ascontiguousarray(G[::-1, ::-1, :]))
    render_preview(os.path.join(docs, 'jonas_clark_entrance.jpg'), 900,
                   np.ascontiguousarray(G[430:570, 630:700, :]))
    render_preview(os.path.join(docs, 'freud_statue.jpg'), 900,
                   np.ascontiguousarray(G[395:460, 540:600, :40]))
    print('wrote %d chunks, %d voxels -> %s' % (n_chunks, n_vox, out))


if __name__ == '__main__':
    main()
