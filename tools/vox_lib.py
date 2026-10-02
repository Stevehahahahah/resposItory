"""Small voxel toolkit used by generate_map.py.

One numpy grid G (1 voxel = 0.1 m, Teardown scale) plus helpers to draw
primitives, text, interiors and furniture, grow trees, export MagicaVoxel
chunks and render isometric previews.

Grid axes: x, y horizontal, z up.  Teardown axes: (x, z, -y).
"""

import math
import struct

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
 PAINT_WHITE, TILE, CROSSWALK) = 73, 74, 75, 76, 77, 78, 79, 80, 81
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
    PAINT_WHITE: (230, 230, 225), TILE: (196, 190, 178), CROSSWALK: (138, 62, 52),
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
NX, NY, NZ = 1408, 1280, 256
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


def c_letter(cx, cy, z, r_in, r_out, c, plane='xy', y_plane=None, open_angle=0.0):
    """A ring with a gap facing open_angle (radians, 0 = +a): the letter C,
    flat on the floor (plane='xy') or in a wall plane y_plane (plane='xz')."""
    for a in range(int(cx - r_out) - 1, int(cx + r_out) + 2):
        for b in range(int(cy - r_out) - 1, int(cy + r_out) + 2):
            da, db = a + 0.5 - cx, b + 0.5 - cy
            d = math.hypot(da, db)
            rel = (math.atan2(db, da) - open_angle + math.pi) % (2 * math.pi) - math.pi
            if r_in <= d < r_out and abs(rel) > 0.75:
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
    'B': ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
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


def draw_text_x(s, y_center, z_top, x_face, c, reading_dir=1):
    """Write text on a wall facing +x (reading_dir=+1 reads towards +y) or -x
    (reading_dir=-1)."""
    w = text_width(s)
    start = y_center - reading_dir * (w // 2)
    for i, ch in enumerate(s):
        for row, line in enumerate(FONT[ch]):
            for col, px in enumerate(line):
                if px == '#':
                    y = start + reading_dir * (i * 6 + col)
                    box(x_face, x_face + 1, y, y + 1, z_top - row, z_top - row + 1, c)


def draw_text_flat(s, x_center, y_top, z, c, stretch=2):
    """Road marking: letters lying on the ground, read from the -y side."""
    w = text_width(s)
    start = x_center - w // 2
    for i, ch in enumerate(s):
        for row, line in enumerate(FONT[ch]):
            for col, px in enumerate(line):
                if px == '#':
                    x = start + i * 6 + col
                    y = y_top - row * stretch
                    box(x, x + 1, y - stretch + 1, y + 1, z, z + 1, c)


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


def interior_wall_y(x, y0, y1, z0, z1, doors, door_w=12, door_h=24, col=PLASTER):
    """Wall along y at x..x+2 with framed door openings centred at `doors`."""
    box(x, x + 2, y0, y1, z0, z1, col)
    for dy in doors:
        box(x, x + 2, dy - door_w // 2 - 1, dy + door_w // 2 + 1, z0, z0 + door_h + 1, DOOR_WOOD)
        box(x, x + 2, dy - door_w // 2, dy + door_w // 2, z0, z0 + door_h, 0)


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


def stairs_y(y_bottom, lane, z_base, z_top, direction=1, rails=('-x', '+x'), run=3):
    """Like stairs() but running along y in `lane` (an x range)."""
    x0, x1 = lane
    rise = z_top - z_base
    steps = int(math.ceil(rise / 2.0))
    for i in range(steps):
        top = z_base + int(round((i + 1) * rise / steps))
        ya = y_bottom + i * run if direction > 0 else y_bottom - (i + 1) * run
        box(x0, x1, ya, ya + run, z_base, top, CONCRETE2)
    y_top = y_bottom + direction * steps * run
    hy0, hy1 = min(y_bottom, y_top) - 4, max(y_bottom, y_top) + 4
    box(x0 - 1, x1 + 1, hy0, hy1, z_top - 2, z_top, 0)
    if '-x' in rails:
        railing_y(x0 - 2, hy0, hy1, z_top)
    if '+x' in rails:
        railing_y(x1 + 1, hy0, hy1, z_top)
    railing_x(x0 - 2, x1 + 2, hy0 - 1 if direction > 0 else hy1, z_top)


def ceiling_lights(x0, x1, y0, y1, z_ceiling, n=2):
    """n light panels along the longer side of the rectangle."""
    for i in range(n):
        if x1 - x0 >= y1 - y0:
            cx, cy = x0 + (x1 - x0) * (2 * i + 1) // (2 * n), (y0 + y1) // 2
        else:
            cx, cy = (x0 + x1) // 2, y0 + (y1 - y0) * (2 * i + 1) // (2 * n)
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
    """A rectangular room whose door (corridor) wall is on side `door`
    ('+y', '-y', '+x' or '-x'); the window wall is opposite.

    put() takes local coordinates: v runs from the window wall towards the
    door wall, u runs along the walls (to the right when facing the door).
    Facings are local too: '+y' = towards the door, '-y' = towards the
    window, '+x' / '-x' = along +u / -u.  w and d are the local extents."""

    _FMAP = {'+y': {'-y': '-y', '+x': '+x', '+y': '+y', '-x': '-x'},
             '-y': {'-y': '+y', '+x': '-x', '+y': '-y', '-x': '+x'},
             '+x': {'-y': '-x', '+y': '+x', '+x': '-y', '-x': '+y'},
             '-x': {'-y': '+x', '+y': '-x', '+x': '+y', '-x': '-y'}}

    def __init__(self, x0, x1, y0, y1, z, door='+y'):
        self.x0, self.x1, self.y0, self.y1, self.z, self.door = x0, x1, y0, y1, z, door
        if door in ('+y', '-y'):
            self.w, self.d = x1 - x0, y1 - y0
        else:
            self.w, self.d = y1 - y0, x1 - x0

    def put(self, parts, u, v, facing='-y', dz=0):
        Wl, Dl = footprint(parts, facing)
        f = self._FMAP[self.door][facing]
        if self.door == '+y':
            x, y = self.x0 + u, self.y0 + v
        elif self.door == '-y':
            x, y = self.x1 - u - Wl, self.y1 - v - Dl
        elif self.door == '+x':
            x, y = self.x0 + v, self.y1 - u - Wl
        else:
            x, y = self.x1 - v - Dl, self.y0 + u
        place(parts, x, y, self.z + dz, f)

    def door_world(self):
        """World coordinate (along the corridor wall) of the standard door at u = 14."""
        return {'+y': self.x0 + 14, '-y': self.x1 - 14,
                '+x': self.y1 - 14, '-x': self.y0 + 14}[self.door]


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
