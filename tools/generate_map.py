#!/usr/bin/env python3
"""Generate a Teardown map of Clark University (Worcester, MA).

The layout follows aerial imagery of the real campus, seen from Main Street:

        +--------------------------------------------------------+
        | [T]             Jonas Clark Hall (1887)            [T] |
        +--------------------------+-----------------------------+
   +------+        beds    [clock / entrance]    beds
   |  UC  |               Red Square (Freud statue)
   | 1990 |   ~~~~~~~~~~~ the Green with its big trees ~~~~~~~~~~~~~~~
   +------+                         |
   |Tilton|                         |  main walk
   | Hall |                    [ "C" gate ]
   +------+ ===================================================== sidewalk
                    Main Street (bus/bike lane, 4 lanes)

* Jonas Clark Hall: 205 x 65 ft (62.5 x 20 m), four-storey wings, a
  five-storey centre with the clock and taller end pavilions.
* Higgins University Center: along the left (south) side of the Green.
  Tilton Hall, the old library with the vaulted Great Room, sits at the
  Main Street end; the 1990 building runs back towards Jonas Clark Hall.
* Both buildings have furnished interiors.

Grid: x along Main Street (to the right / north), y away from Main Street,
z up; 1 voxel = 0.1 m.  Teardown axes: (x, z, -y).

Usage:  python3 tools/generate_map.py [output_dir]
"""

import math
import os
import shutil
import sys

import numpy as np

from vox_lib import *  # noqa: F401,F403  (palette, grid, primitives, furniture, export)

AXIS = 742                                    # Jonas Clark Hall / main gate centre line
ROAD0, ROAD1, PROP = 40, 210, 250             # far curb, near curb, back of the sidewalk

# Jonas Clark Hall
JX0, JX1, JY0, JY1 = 430, 1055, 1010, 1210
JL = [1, 41, 81, 121, 161]                    # ground, 2nd, 3rd, 4th floor, wing roof
JP4 = 201                                     # top of the centre / end pavilions
PAV = (687, 797)                              # centre pavilion
TOWERS = ((430, 490), (995, 1055))            # end pavilions
J_ROOMS_X = [(433, 490), (492, 556), (558, 622), (624, 687), (689, 797),
             (799, 863), (865, 929), (931, 995), (997, 1052)]
J_CROSS = (490, 556, 622, 687, 797, 863, 929, 995)
J_FRONT, J_BACK = (1013, 1085), (1117, 1207)
S_BAYS = (525, 589, 653)                      # window bays of the south wing
N_BAYS = (832, 896, 960)
PILASTERS = (494, 556, 622, 683, 801, 863, 929, 991)

# Higgins University Center
TX0, TX1, TY0, TY1 = 90, 360, 300, 600        # Tilton Hall (old library)
UX0, UX1, UY0, UY1 = 110, 350, 600, 1080      # the 1990 building
UL = [1, 41, 81, 121, 161]
U_ROOMS = [(603, 695), (697, 790), (792, 885), (887, 980), (982, 1077)]
T_DOOR = 485                                  # Tilton Hall's door on the Green
VEST = (828, 932)                             # glass entrance of the 1990 building


def hip(x0, x1, y0, y1, z, layers, col, flat_top=True):
    """Hollow hipped roof rising one voxel per two inwards."""
    k = 0
    while k < layers:
        a0, a1, b0, b1 = x0 + 2 * k, x1 - 2 * k, y0 + 2 * k, y1 - 2 * k
        if a1 - a0 <= 2 or b1 - b0 <= 2:
            break
        box(a0, a1, b0, b1, z + k, z + k + 1, col)
        if a1 - a0 > 12 and b1 - b0 > 12 and not (flat_top and k == layers - 1):
            box(a0 + 6, a1 - 6, b0 + 6, b1 - 6, z + k, z + k + 1, 0)
        k += 1


# --------------------------------------------------------------------------
# Jonas Clark Hall
# --------------------------------------------------------------------------
def jch_window(face, c, z0, z1, kind, w=12):
    """Window in the front ('f'), back ('b') or end ('w'/'e') walls."""
    a0, a1 = c - w // 2, c + w // 2
    arch = kind == 'arch'
    if face == 'f':
        yf = JY0 - 10 if PAV[0] <= c < PAV[1] else (JY0 - 6 if c < 490 or c >= 995 else JY0)
        opening('x', a0, a1, z0, z1, yf, JY0 + 3, yf + 1, arch=arch)
        if arch:
            arch_ring('x', a0, a1, z1, yf - 1, yf, TRIM)
        else:
            box(a0 - 2, a1 + 2, yf - 1, yf, z1, z1 + 3, TRIM)
            box(a0 - 1, a1 + 1, yf - 1, yf, z0 - 2, z0, TRIM)
    elif face == 'b':
        opening('x', a0, a1, z0, z1, JY1 - 3, JY1, JY1 - 2, arch=arch)
        if arch:
            arch_ring('x', a0, a1, z1, JY1, JY1 + 1, TRIM)
        else:
            box(a0 - 2, a1 + 2, JY1, JY1 + 1, z1, z1 + 3, TRIM)
    else:
        xw = JX0 if face == 'w' else JX1 - 3
        out = JX0 - 1 if face == 'w' else JX1
        opening('y', a0, a1, z0, z1, xw, xw + 3, xw + 1, arch=arch)
        if arch:
            arch_ring('y', a0, a1, z1, out, out + 1, TRIM)
        else:
            box(out, out + 1, a0 - 2, a1 + 2, z1, z1 + 3, TRIM)


ROWS = [(10, 32, 'rect'), (JL[1] + 9, JL[1] + 31, 'rect'), (JL[2] + 9, JL[2] + 23, 'arch'),
        (JL[3] + 9, JL[3] + 31, 'rect')]


def jonas_clark_hall():
    T = 3
    px0, px1 = PAV
    box(JX0 - 2, JX1 + 2, JY0 - 12, JY1 + 2, 0, 1, CONCRETE)
    shell(JX0, JX1, JY0, JY1, 1, JL[4], BRICK, T)
    box(px0, px1, JY0 - 10, JY0, 1, JL[4], BRICK)             # centre projects 1 m
    for tx0, tx1 in TOWERS:
        box(tx0, tx1, JY0 - 6, JY0, 1, JL[4], BRICK)          # end pavilions 0.6 m

    def bands(z, h=2):
        box(JX0 - 1, JX1 + 1, JY0 - 1, JY1 + 1, z, z + h, TRIM)
        box(px0 - 1, px1 + 1, JY0 - 11, JY0, z, z + h, TRIM)
        for tx0, tx1 in TOWERS:
            box(tx0 - 1, tx1 + 1, JY0 - 7, JY0, z, z + h, TRIM)
        box(JX0 + T, JX1 - T, JY0 + T, JY1 - T, z, z + h, 0)

    recolor(JX0 - 2, JX1 + 2, JY0 - 12, JY1 + 2, 1, JL[1] - 2, BRICK, GRANITE)   # stone base
    for z in (JL[1] - 2, JL[2] - 2, JL[3] - 2):
        bands(z)

    # pilasters between the window bays, rising above the cornice as pinnacles
    for px in PILASTERS:
        for yf, ya, yb in ((JY0, JY0 - 2, JY0), (JY1, JY1, JY1 + 2)):
            box(px - 4, px + 4, ya, yb, JL[1], JL[4], BRICK)
    # wing cornice and low hipped slate roof
    for k, (z0, z1) in enumerate(((161, 164), (164, 167), (167, 170))):
        p = k + 1
        box(JX0 - 1 - p, JX1 + 1 + p, JY0 - 1 - p, JY1 + 1 + p, z0, z1, TRIM)
    box(JX0 + T, JX1 - T, JY0 + T, JY1 - T, 161, 170, 0)
    hip(JX0 - 4, JX1 + 4, JY0 - 4, JY1 + 4, 170, 28, SLATE)
    for px in PILASTERS:
        for y0 in (JY0 - 4, JY1 - 4):
            box(px - 4, px + 4, y0, y0 + 8, 161, 184, BRICK)
            box(px - 5, px + 5, y0 - 1, y0 + 9, 184, 186, TRIM)
            box(px - 3, px + 3, y0 + 1, y0 + 7, 186, 189, TRIM)
            box(px - 1, px + 1, y0 + 3, y0 + 5, 189, 192, TRIM)

    # centre and end pavilions rise one storey higher
    for x0, x1, yf in ((px0, px1, JY0 - 10),) + tuple((a, b, JY0 - 6) for a, b in TOWERS):
        box(x0 + T, x1 - T, yf + T, JY1 - T, JL[4], JP4 + 6, 0)
        shell(x0, x1, yf, JY1, JL[4], JP4, BRICK, T)
        box(x0 - 1, x1 + 1, yf - 1, JY1 + 1, JL[4] - 2, JL[4], TRIM)
        for k, (z0, z1) in enumerate(((JP4, JP4 + 3), (JP4 + 3, JP4 + 6))):
            p = k + 1
            box(x0 - p, x1 + p, yf - p, JY1 + p, z0, z1, TRIM)
        box(x0 + T, x1 - T, yf + T, JY1 - T, JL[4] - 2, JP4 + 6, 0)
    hip(px0 - 3, px1 + 3, JY0 - 13, JY1 + 3, JP4 + 6, 26, SLATE)
    for tx0, tx1 in TOWERS:
        hip(tx0 - 3, tx1 + 3, JY0 - 9, JY1 + 3, JP4 + 6, 40, SLATE)

    # ---- windows ---------------------------------------------------------
    wing_cols = [c + d for c in S_BAYS + N_BAYS for d in (-20, 0, 20)]
    for z0, z1, kind in ROWS:
        for c in wing_cols:
            jch_window('f', c, z0, z1, kind)
            jch_window('b', c, z0, z1, kind)
        for c in (460, 1025):
            jch_window('f', c, z0, z1, kind, 14)
            jch_window('b', c, z0, z1, kind, 14)
        for c in (1060, 1110, 1160):
            jch_window('w', c, z0, z1, kind)
            jch_window('e', c, z0, z1, kind)
        for c in (700, 784):
            jch_window('f', c, z0, z1, kind)
        for c in (712, 742, 772):
            jch_window('b', c, z0, z1, kind)
    for c in (732, 752):                                          # centre, upper floors
        for z0, z1, kind in ROWS[2:]:
            jch_window('f', c, z0, z1, kind, 10)
    for c in (712, 742, 772):                                     # 5th storey of the centre
        jch_window('f', c, JL[4] + 9, JL[4] + 25, 'arch')
    for c in (452, 468, 1017, 1033):                              # 5th storey of the ends
        jch_window('f', c, JL[4] + 9, JL[4] + 25, 'arch', 10)
    for x0, x1 in TOWERS:
        for c in (1060, 1110, 1160):
            if x0 == 430:
                jch_window('w', c, JL[4] + 9, JL[4] + 25, 'arch')
            else:
                jch_window('e', c, JL[4] + 9, JL[4] + 25, 'arch')
    # radiators under the windows
    for zf in JL[:4]:
        for c in wing_cols + [460, 1025]:
            radiator('x', c - 7, c + 7, JY0 + 3, JY0 + 5, zf)
            radiator('x', c - 7, c + 7, JY1 - 5, JY1 - 3, zf)

    # ---- entrance, name blocks and the clock ------------------------------
    yf = JY0 - 10
    opening('x', 727, 757, 1, 24, yf, JY0 + 3)
    arch_ring('x', 727, 757, 24, yf - 1, yf, GRANITE, thick=3)
    opening('x', 727, 757, 24, 25, yf, JY0 + 3, yf + 4, arch=True)
    box(727, 757, yf, JY0 + 3, 24, 25, DOOR_WOOD)
    box(728, 730, JY0 + 3, JY0 + 17, 1, 24, DOOR_WOOD)                # open door leaves
    box(754, 756, JY0 + 3, JY0 + 17, 1, 24, DOOR_WOOD)
    for word, z0 in (("1887", 45), ("UNIVERSITY", 56), ("CLARK", 67)):
        box(709, 776, yf - 2, yf, z0, z0 + 11, GRANITE)
        draw_text(word, AXIS, z0 + 8, yf - 2, GRANITE_TEXT)
    cz = JP4 + 6
    box(px0 + 10, px1 - 10, yf, yf + 8, cz, cz + 30, BRICK)            # clock gable
    box(px0 + 8, px1 - 8, yf - 2, yf + 10, cz + 30, cz + 34, TRIM)
    for x in (px0 + 8, px1 - 14):
        box(x, x + 6, yf - 2, yf + 8, cz, cz + 38, BRICK3)
        box(x - 1, x + 7, yf - 3, yf + 9, cz + 38, cz + 40, TRIM)
    ccz = cz + 16
    for x in range(AXIS - 13, AXIS + 14):
        for z in range(ccz - 13, ccz + 14):
            d = math.hypot(x + 0.5 - AXIS, z + 0.5 - ccz)
            if d < 10.5:
                box(x, x + 1, yf - 1, yf, z, z + 1, WHITEBOARD)
            elif d < 12.5:
                box(x, x + 1, yf - 1, yf, z, z + 1, TRIM)
    for t in range(7):                                                 # hands at 10:10
        for ang, L in ((150, 6), (30, 9)):
            if t <= L:
                a = math.radians(ang)
                x, z = int(AXIS + t * math.cos(a)), int(ccz + t * math.sin(a))
                box(x, x + 1, yf - 2, yf - 1, z, z + 1, METAL_DARK)
    for ang in (0, 90, 180, 270):
        a = math.radians(ang)
        x, z = int(AXIS + 8.5 * math.cos(a)), int(ccz + 8.5 * math.sin(a))
        box(x, x + 1, yf - 2, yf - 1, z, z + 1, METAL_DARK)
    for x in (598, 874):                                               # chimneys
        box(x, x + 12, 1170, 1182, 185, 226, BRICK)
        box(x - 1, x + 13, 1169, 1183, 226, 229, GRANITE)


def jch_structure():
    ix0, ix1, iy0, iy1 = JX0 + 3, JX1 - 3, JY0 + 3, JY1 - 3
    for z in JL[1:4]:
        floor_slab(ix0, ix1, iy0, iy1, z)
    floor_slab(ix0, ix1, iy0, iy1, JL[4], wood=False)
    for x0, x1 in ((PAV[0] + 3, PAV[1] - 3),) + tuple((a + 3, b - 3) for a, b in TOWERS):
        box(x0, x1, iy0, iy1, JL[4] - 1, JL[4], FLOOR_WOOD)
        floor_slab(x0, x1, iy0, iy1, JP4, wood=False)
    side = [r for r in J_ROOMS_X if r[0] != 689]
    for lvl in range(4):
        zb, zt = JL[lvl], JL[lvl + 1]
        top = zt - 2
        interior_wall_x(ix0, ix1, 1085, zb, top, [x0 + 14 for x0, x1 in side] + ([] if lvl == 0 else [AXIS]))
        interior_wall_x(ix0, ix1, 1115, zb, top, [x1 - 14 for x0, x1 in side])
        for x in J_CROSS:
            box(x, x + 2, iy0, 1085, zb, top, PLASTER)
            box(x, x + 2, 1117, iy1, zb, top, PLASTER)
        box(689, 797, 1115, 1117, zb, top, 0)                 # stair hall open to the corridor
        if lvl == 0:
            box(689, 797, 1085, 1087, zb, top, 0)             # entrance hall open to the corridor
        recolor(ix0, ix1, 1086, 1087, zb, zb + 9, PLASTER, DOOR_WOOD)
        recolor(ix0, ix1, 1115, 1116, zb, zb + 9, PLASTER, DOOR_WOOD)
        for x in range(ix0 + 30, ix1 - 20, 60):
            box(x - 4, x + 4, 1099, 1103, top - 1, top, LAMP)
        for i, x in enumerate((525, 595, 830, 900)):
            place(bulletin_board(16, 10, lvl * 10 + i), x, 1087, zb + 12, '+y')
    stairs(700, (1125, 1145), JL[0], JL[1], +1)
    stairs(760, (1152, 1172), JL[1], JL[2], -1)
    stairs(700, (1125, 1145), JL[2], JL[3], +1)
    stairs(760, (1152, 1172), JL[3], JL[4], -1)


def jch_room(i, zone, lvl):
    x0, x1 = J_ROOMS_X[i]
    if zone == 'f':
        return Room(x0, x1, J_FRONT[0], J_FRONT[1], JL[lvl], '+y')
    return Room(x0, x1, J_BACK[0], J_BACK[1], JL[lvl], '-y')


# ---- room types (local room coordinates, see vox_lib.Room) -----------------
def classroom(rm, seed=0):
    cv = rm.d // 2
    rm.put(board(40, seed=seed), 0, cv - 20, '+x')
    rm.put(teacher_desk(), 8, cv - 7, '+x')
    for u in range(30, rm.w - 12, 14):
        for v in range(6, rm.d - 12, 16):
            rm.put(student_desk(), u, v, '-x')
    rm.put(painting(10, 8, 'landscape'), rm.w - 1, cv - 5, '-x', dz=14)


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
    bw = min(30, rm.d - 12)
    rm.put(whiteboard(bw, seed), 0, rm.d // 2 - bw // 2, '+x')
    rm.put(bulletin_board(16, 10, seed), rm.w - 1, rm.d // 2 - 8, '-x', dz=12)
    rm.put(plant(), rm.w - 6, 1)


def storage(rm, seed=0):
    r = np.random.default_rng(seed)
    for u in range(4, rm.w - 10, 9):
        for v in range(3, rm.d - 24, 9):
            if r.random() < 0.6:
                for k in range(int(r.integers(1, 3))):
                    rm.put(crate(7), u, v, dz=k * 7)
    rm.put(bookshelf(12, 20, seed, METAL_GRAY, (BOOK_TAN, DOOR_WOOD, BENCH_WOOD)), rm.w - 3, rm.d - 22, '-x')


def copy_room(rm):
    rm.put(copier(), 6, 3)
    rm.put(copier(), 20, 3)
    rm.put(bookshelf(12, 20, 5, METAL_GRAY, (PLASTER, WHITEBOARD, BOOK_TAN)), rm.w - 3, 10, '-x')
    rm.put(crate(6), 8, 30)
    rm.put(crate(6), 16, 30)


def conference_room(rm, seed=0):
    tw = min(48, rm.w - 16)
    W, D = extent(conference_table(tw, 14))
    rm.put(conference_table(tw, 14, DOOR_WOOD, SOFA_BROWN), (rm.w - W) // 2, (rm.d - D) // 2)
    rm.put(board(36, seed=seed), 0, rm.d // 2 - 18, '+x')
    rm.put(plant(), rm.w - 6, 1)


def reading_room(rm):
    rm.put(conference_table(min(30, rm.w - 12), 10, BENCH_WOOD, DOOR_WOOD), 6, 3)
    for u in range(14, rm.w - 6, 18):
        for i, v in enumerate((30, 43)):
            rm.put(bookshelf(12, 22, u + i), u - 3, v, '-x')
            rm.put(bookshelf(12, 22, u + i + 50), u, v, '+x')


def seminar_room(rm, seed=0):
    W, D = extent(conference_table(48, 14))
    rm.put(conference_table(48, 14), (rm.w - W) // 2, (rm.d - D) // 2)
    rm.put(board(40, seed=seed), rm.w - 2, rm.d // 2 - 20, '-x')
    for i, v in enumerate((6, 19, 32, 45)):
        rm.put(bookshelf(12, 22, 60 + i), 0, v, '+x')


def president_office(rm):
    rm.put(rug(60, 40, RUG_RED), 24, 4)
    rm.put(exec_desk(), 42, 6, '+y')
    rm.put(armchair(SOFA_BROWN), 39, 27, '-y')
    rm.put(armchair(SOFA_BROWN), 61, 27, '-y')
    for i, v in enumerate((4, 17, 30, 43)):
        rm.put(bookshelf(12, 24, 40 + i), 0, v, '+x')
    rm.put(sofa(20, SOFA_BROWN), rm.w - 8, 30, '-x')
    rm.put(coffee_table(), rm.w - 20, 35, '+x')
    rm.put(armchair(SOFA_BROWN), rm.w - 34, 36, '+x')
    rm.put(painting(16, 12, 'portrait'), rm.w - 1, 32, '-x', dz=14)
    rm.put(plant(), 2, 62)
    rm.put(plant(), rm.w - 6, 2)
    x, y = rm.x0 + 10, rm.y0 + 60                                      # Clark scarlet flag
    box(x, x + 1, y, y + 1, rm.z, rm.z + 26, BRONZE_LIGHT)
    box(x - 1, x + 2, y - 1, y + 2, rm.z, rm.z + 1, BRONZE_LIGHT)
    box(x, x + 1, y + 1, y + 11, rm.z + 14, rm.z + 25, RUG_RED)


def entrance_hall(z):
    box(732, 752, JY0 + 3, 1117, z, z + 1, RUG_RED)                   # runner to the stairs
    box(732, 733, JY0 + 3, 1117, z, z + 1, BOOK_TAN)
    box(751, 752, JY0 + 3, 1117, z, z + 1, BOOK_TAN)
    for y in (1025, 1055):
        place(display_case(16, 6, BRONZE), 690, y, z, '+x')          # 1909: Freud at Clark
        place(display_case(16, 6, BRONZE_LIGHT), 791, y, z, '-x')
        place(painting(12, 14, 'portrait'), 689, y + 2, z + 20, '+x')
        place(painting(12, 14, 'portrait'), 796, y + 2, z + 20, '-x')
    for y in (1035, 1070):
        box(741, 743, y - 1, y + 1, JL[1] - 8, JL[1] - 2, METAL_DARK)
        box(739, 745, y - 3, y + 3, JL[1] - 11, JL[1] - 8, LAMP)


def history_room(z):
    """The fifth storey under the clock: a small museum of the 1909 lectures."""
    rm = Room(690, 794, JY0 - 7, 1112, z, '+y')
    rm.put(rug(60, 40, RUG_RED), 22, 30)
    rm.put(podium(), 49, 22, '+y')
    for v in (40, 50, 60):
        for u in range(28, 80, 8):
            rm.put(chair(BENCH_WOOD, DOOR_WOOD), u, v, '-y')
    for v in (20, 60):
        rm.put(display_case(16, 6, BRONZE), 0, v, '+x')
        rm.put(display_case(16, 6, BRONZE_LIGHT), rm.w - 6, v, '-x')
    rm.put(painting(16, 18, 'portrait'), 44, rm.d - 1, '+y', dz=12)


def tower_lounge(x0, x1, z):
    rm = Room(x0 + 3, x1 - 3, JY0 - 3, JY1 - 3, z, '+y')
    rm.put(rug(30, 40, RUG_BLUE), (rm.w - 30) // 2, 40)
    rm.put(armchair(), 6, 50, '+x')
    rm.put(armchair(), rm.w - 15, 50, '-x')
    rm.put(coffee_table(), (rm.w - 6) // 2, 54, '+x')
    for v in (100, 113, 126):
        rm.put(bookshelf(12, 22, v), 0, v, '+x')


def furnish_jch():
    R = jch_room
    plan = {
        0: {'f': {0: 'office', 1: 'class', 2: 'class', 3: 'office', 5: 'office', 6: 'class', 7: 'class',
                  8: 'office'},
            'b': {0: 'office', 1: 'class', 2: 'class', 3: 'meeting', 5: 'meeting', 6: 'class', 7: 'class',
                  8: 'office'}},
        1: {'f': {0: 'office', 1: 'class', 2: 'class', 3: 'office', 4: 'office2', 5: 'office', 6: 'class',
                  7: 'class', 8: 'office'},
            'b': {0: 'office', 1: 'class', 2: 'class', 3: 'storage', 5: 'copy', 6: 'class', 7: 'class',
                  8: 'office'}},
        2: {'f': {0: 'office', 1: 'office2', 2: 'conference', 3: 'office', 4: 'president', 5: 'office',
                  6: 'office2', 7: 'conference', 8: 'office'},
            'b': {0: 'office', 1: 'class', 2: 'class', 3: 'copy', 5: 'storage', 6: 'class', 7: 'class',
                  8: 'office'}},
        3: {'f': {0: 'office', 1: 'class', 2: 'class', 3: 'reading', 4: 'seminar', 5: 'reading', 6: 'class',
                  7: 'class', 8: 'office'},
            'b': {0: 'office', 1: 'class', 2: 'class', 3: 'storage', 5: 'storage', 6: 'class', 7: 'class',
                  8: 'office'}},
    }
    seed = 0
    for lvl, zones in plan.items():
        for zone, rooms in zones.items():
            for i, kind in rooms.items():
                rm = R(i, zone, lvl)
                seed += 1
                if kind == 'class':
                    classroom(rm, seed)
                elif kind == 'office':
                    office(rm, 1, seed, (RUG_BLUE, CARPET2, RUG_RED)[seed % 3])
                elif kind == 'office2':
                    office(rm, 2, seed, RUG_RED)
                elif kind == 'meeting':
                    meeting_room(rm, seed)
                elif kind == 'storage':
                    storage(rm, seed)
                elif kind == 'copy':
                    copy_room(rm)
                elif kind == 'conference':
                    conference_room(rm, seed)
                elif kind == 'reading':
                    reading_room(rm)
                elif kind == 'seminar':
                    seminar_room(rm, seed)
                elif kind == 'president':
                    president_office(rm)
    entrance_hall(JL[0])
    history_room(JL[4])
    for x0, x1 in TOWERS:
        tower_lounge(x0, x1, JL[4])
    for lvl in range(4):
        ceil = JL[lvl + 1] - 2
        for x0, x1 in J_ROOMS_X:
            for y0, y1 in (J_FRONT, J_BACK):
                ceiling_lights(x0, x1, y0, y1, ceil, 2 if x1 - x0 > 70 else 1)
    for x0, x1 in ((PAV[0] + 3, PAV[1] - 3),) + tuple((a + 3, b - 3) for a, b in TOWERS):
        ceiling_lights(x0, x1, JY0, JY1, JP4 - 2, 3)


# --------------------------------------------------------------------------
# Higgins University Center: Tilton Hall (old library) + the 1990 building
# --------------------------------------------------------------------------
def tilton_building():
    T = 3
    box(TX0, TX1, TY0, TY1, 0, 1, CONCRETE)
    shell(TX0, TX1, TY0, TY1, 1, 150, UC_BRICK, T)
    recolor(TX0 - 2, TX1 + 2, TY0 - 2, TY1 + 2, 1, 9, UC_BRICK, GRANITE_DARK)
    box(TX0 - 1, TX1 + 1, TY0 - 1, TY1 + 1, 39, 42, CONCRETE_LIGHT)
    box(TX0 + T, TX1 - T, TY0 + T, TY1 - T, 39, 42, 0)
    for k, (z0, z1) in enumerate(((150, 153), (153, 156), (156, 160))):
        p = k + 1
        box(TX0 - 1 - p, TX1 + 1 + p, TY0 - 1 - p, TY1 + 1 + p, z0, z1, CONCRETE_LIGHT)
    box(TX0 + T, TX1 - T, TY0 + T, TY1 - T, 150, 160, 0)
    box(TX0 - 1, TX1 + 1, TY0 - 1, TY1 + 1, 118, 121, CONCRETE_LIGHT)      # band at the vault
    box(TX0 + T, TX1 - T, TY0 + T, TY1 - T, 118, 121, 0)

    def win(face, c, z0, z1, w, arch):
        a0, a1 = c - w // 2, c + w // 2
        if face == 'n':        # facing the Green (+x)
            opening('y', a0, a1, z0, z1, TX1 - 3, TX1, TX1 - 2, arch=arch)
            if arch:
                arch_ring('y', a0, a1, z1, TX1, TX1 + 1, CONCRETE_LIGHT)
            box(TX1, TX1 + 1, a0 - 1, a1 + 1, z0 - 2, z0, CONCRETE_LIGHT)
            box(TX1 - 2, TX1 - 1, c, c + 1, z0, z1 + (w // 2 if arch else 0), METAL_DARK)
        elif face == 's':
            opening('y', a0, a1, z0, z1, TX0, TX0 + 3, TX0 + 1, arch=arch)
            if arch:
                arch_ring('y', a0, a1, z1, TX0 - 1, TX0, CONCRETE_LIGHT)
            box(TX0 - 1, TX0, a0 - 1, a1 + 1, z0 - 2, z0, CONCRETE_LIGHT)
        else:                  # facing Main Street (-y)
            opening('x', a0, a1, z0, z1, TY0, TY0 + 3, TY0 + 1, arch=arch)
            if arch:
                arch_ring('x', a0, a1, z1, TY0 - 1, TY0, CONCRETE_LIGHT)
            box(a0 - 1, a1 + 1, TY0 - 1, TY0, z0 - 2, z0, CONCRETE_LIGHT)
            box(c, c + 1, TY0 + 1, TY0 + 2, z0, z1 + (w // 2 if arch else 0), METAL_DARK)

    for c in (335, 385, 435, 535, 580):
        win('n', c, 10, 32, 14, False)
        win('s', c, 10, 32, 14, False)
    win('s', T_DOOR, 10, 32, 14, False)
    for c in (125, 170, 225, 280, 325):
        win('e', c, 10, 32, 14, False)
    for c in (335, 385, 435, T_DOOR, 535, 580):                      # Great Room windows
        win('n', c, 55, 106, 18, True)
        win('s', c, 55, 106, 18, True)
    for c in (125, 170, 225, 280, 325):
        win('e', c, 55, 106, 18, True)
    for c in (335, 385, 435, T_DOOR, 535, 580):                      # attic windows
        win('n', c, 128, 142, 10, False)
        win('s', c, 128, 142, 10, False)
    for z in (72, 88):                                                # transoms
        recolor(TX1 - 2, TX1 - 1, TY0, TY1, z, z + 1, GLASS, METAL_DARK)
        recolor(TX0 + 1, TX0 + 2, TY0, TY1, z, z + 1, GLASS, METAL_DARK)
        recolor(TX0, TX1, TY0 + 1, TY0 + 2, z, z + 1, GLASS, METAL_DARK)
    # door on the Green with a stone surround and pediment
    opening('y', T_DOOR - 12, T_DOOR + 12, 1, 26, TX1 - 3, TX1)
    box(TX1, TX1 + 2, T_DOOR - 16, T_DOOR - 12, 1, 30, CONCRETE_LIGHT)
    box(TX1, TX1 + 2, T_DOOR + 12, T_DOOR + 16, 1, 30, CONCRETE_LIGHT)
    box(TX1, TX1 + 3, T_DOOR - 18, T_DOOR + 18, 30, 33, CONCRETE_LIGHT)
    for k in range(9):
        box(TX1, TX1 + 2, T_DOOR - 16 + 2 * k, T_DOOR + 16 - 2 * k, 33 + k, 34 + k, CONCRETE_LIGHT)
    box(TX1 - 16, TX1 - 3, T_DOOR - 12, T_DOOR - 10, 1, 24, DOOR_WOOD)   # open door leaves
    box(TX1 - 16, TX1 - 3, T_DOOR + 10, T_DOOR + 12, 1, 24, DOOR_WOOD)
    # hipped slate roof with a cross gable over the door bay
    hip(TX0 - 4, TX1 + 4, TY0 - 4, TY1 + 4, 160, 80, SLATE)
    for k in range(31):
        ya, yb, z = T_DOOR - 34 + k, T_DOOR + 34 - k, 160 + k
        if yb - ya <= 2:
            break
        box(300, TX1 + 6, ya, ya + 2, z, z + 1, SLATE)
        box(300, TX1 + 6, yb - 2, yb, z, z + 1, SLATE)
        box(TX1 - 1, TX1 + 2, ya + 2, yb - 2, z, z + 1, UC_BRICK)
        box(TX1 + 2, TX1 + 6, ya, ya + 2, z, z + 1, CONCRETE_LIGHT)
        box(TX1 + 2, TX1 + 6, yb - 2, yb, z, z + 1, CONCRETE_LIGHT)
    for z in range(166, 184):                                          # round window in the gable
        for y in range(T_DOOR - 9, T_DOOR + 10):
            d = math.hypot(y + 0.5 - T_DOOR, z + 0.5 - 175)
            if d < 6:
                box(TX1 - 1, TX1 + 2, y, y + 1, z, z + 1, GLASS)
            elif d < 8:
                box(TX1 + 2, TX1 + 3, y, y + 1, z, z + 1, CONCRETE_LIGHT)


def tilton_structure():
    ix0, ix1, iy0, iy1 = TX0 + 3, TX1 - 3, TY0 + 3, TY1 - 3
    box(ix0, ix1, iy0, iy1, 0, 1, TILE)
    floor_slab(ix0, ix1, iy0, iy1, UL[1])                               # Great Room floor
    for x0, x1, y0, y1 in ((ix0 - 1, ix0, iy0, iy1), (ix1, ix1 + 1, iy0, iy1),
                           (ix0, ix1, iy0 - 1, iy0), (ix0, ix1, iy1, iy1 + 1)):
        recolor(x0, x1, y0, y1, UL[1], 150, UC_BRICK, WALL_CREAM)
        recolor(x0, x1, y0, y1, UL[1], UL[1] + 12, WALL_CREAM, DOOR_WOOD)
    # segmental barrel vault: 36 ft (11 m) above the floor at the crown
    xc, half, rise, crown = (ix0 + ix1) / 2.0, (ix1 - ix0) / 2.0, 36.0, 156.0
    R = (half * half + rise * rise) / (2 * rise)
    zc = crown - R
    xs = np.arange(ix0, ix1) + 0.5
    zz = np.arange(110, 162) + 0.5
    D = np.hypot(xs[:, None] - xc, zz[None, :] - zc)
    m = (D >= R) & (D < R + 3)
    for y in range(iy0, iy1):
        G[ix0:ix1, y, 110:162][m] = PLASTER
    # stair from the lobby up to the Great Room, openings to the 1990 building
    stairs(120, (565, 585), UL[0], UL[1], +1)
    for zb in (UL[0], UL[1]):
        box(220, 250, TY1 - 3, UY0 + 3, zb, zb + 25, 0)
        box(219, 220, TY1 - 3, UY0 + 3, zb, zb + 26, DOOR_WOOD)
        box(250, 251, TY1 - 3, UY0 + 3, zb, zb + 26, DOOR_WOOD)


def uc_building():
    T = 3
    box(UX0, UX1, UY0, UY1, 0, 1, CONCRETE)
    shell(UX0, UX1, UY0, UY1, 1, 170, UC_BRICK, T)
    recolor(UX0 - 2, UX1 + 2, UY0, UY1 + 2, 1, 8, UC_BRICK, GRANITE_DARK)
    for z in (UL[1] - 2, UL[2] - 2, UL[3] - 2):
        box(UX0 - 1, UX1 + 1, UY0, UY1 + 1, z, z + 3, CONCRETE_LIGHT)
        box(UX0 + T, UX1 - T, UY0 + T, UY1 - T, z, z + 3, 0)
    box(UX0 - 1, UX1 + 1, UY0, UY1 + 1, 170, 173, CONCRETE_LIGHT)
    box(UX0 + 2, UX1 - 2, UY0 + 2, UY1 - 2, 170, 173, 0)

    def win(face, c, z0, z1):
        a0, a1 = c - 7, c + 7
        if face == 'n':
            opening('y', a0, a1, z0, z1, UX1 - 3, UX1, UX1 - 2)
            box(UX1, UX1 + 1, a0 - 1, a1 + 1, z0 - 2, z0, CONCRETE_LIGHT)
            box(UX1, UX1 + 1, a0 - 1, a1 + 1, z1, z1 + 3, UC_BRICK2)
            box(UX1 - 2, UX1 - 1, c, c + 1, z0, z1, METAL_DARK)
        elif face == 's':
            opening('y', a0, a1, z0, z1, UX0, UX0 + 3, UX0 + 1)
            box(UX0 - 1, UX0, a0 - 1, a1 + 1, z0 - 2, z0, CONCRETE_LIGHT)
            box(UX0 - 1, UX0, a0 - 1, a1 + 1, z1, z1 + 3, UC_BRICK2)
        else:
            opening('x', a0, a1, z0, z1, UY1 - 3, UY1, UY1 - 2)
            box(a0 - 1, a1 + 1, UY1, UY1 + 1, z0 - 2, z0, CONCRETE_LIGHT)

    wz = [(10, 34), (UL[1] + 8, UL[1] + 30), (UL[2] + 8, UL[2] + 30), (UL[3] + 8, UL[3] + 28)]
    for lvl, (z0, z1) in enumerate(wz):
        for y0, y1 in U_ROOMS:
            for c in ((y0 + y1) // 2 - 28, (y0 + y1) // 2, (y0 + y1) // 2 + 28):
                if not (lvl < 2 and VEST[0] - 10 < c < VEST[1] + 10):
                    win('n', c, z0, z1)
                win('s', c, z0, z1)
        for c in (140, 175, 234, 290, 325):
            win('w', c, z0, z1)
    # two-storey glass entrance on the Green
    v0, v1 = VEST
    box(UX1, UX1 + 24, v0, v1, 1, 80, GLASS)
    box(UX1, UX1 + 22, v0 + 2, v1 - 2, 1, 78, 0)
    for y in range(v0, v1 + 1, 13):
        box(UX1 + 22, UX1 + 24, y - 1, y + 1, 1, 80, METAL_DARK)
    for x in range(UX1, UX1 + 25, 8):
        box(x - 1, x + 1, v0, v0 + 2, 1, 80, METAL_DARK)
        box(x - 1, x + 1, v1 - 2, v1, 1, 80, METAL_DARK)
    for z in (26, 52):
        box(UX1 + 22, UX1 + 24, v0, v1, z, z + 2, METAL_DARK)
    box(UX1 - 3, UX1 + 26, v0 - 2, v1 + 2, 80, 90, CONCRETE_LIGHT)
    draw_text_x("UNIVERSITY CENTER", (v0 + v1) // 2, 88, UX1 + 26, METAL_DARK, +1)
    box(UX1 + 22, UX1 + 24, (v0 + v1) // 2 - 13, (v0 + v1) // 2 + 13, 1, 25, 0)   # open doors
    box(UX1 - 3, UX1, v0 + 10, v1 - 10, 1, 30, 0)                                  # into the hall
    box(UX1 - 3, UX1, v0 + 10, v1 - 10, 30, 32, METAL_DARK)
    # roof deck furniture: air handlers and a stair penthouse
    for x0, x1, y0, y1, h in ((150, 190, 650, 700, 18), (262, 302, 760, 822, 14), (170, 232, 900, 960, 20)):
        box(x0, x1, y0, y1, UL[4], UL[4] + h, METAL_GRAY)
        for x in range(x0 + 2, x1 - 1, 5):
            box(x, x + 2, y0 - 1, y0, UL[4] + 3, UL[4] + h - 3, METAL_DARK)
    box(120, 200, 990, 1066, UL[4], UL[4] + 32, UC_BRICK)
    box(118, 202, 988, 1068, UL[4] + 32, UL[4] + 35, CONCRETE_LIGHT)


def uc_structure():
    ix0, ix1, iy0, iy1 = UX0 + 3, UX1 - 3, UY0 + 3, UY1 - 3
    box(ix0, ix1, iy0, iy1, 0, 1, TILE)
    for z in UL[1:4]:
        floor_slab(ix0, ix1, iy0, iy1, z, wood=False)
        box(ix0, ix1, iy0, iy1, z - 1, z, CARPET)
    floor_slab(ix0, ix1, iy0, iy1, UL[4], wood=False)
    for lvl in range(4):
        zb, zt = UL[lvl], UL[lvl + 1]
        top = zt - 2
        merged_n = {0: (697, 980), 1: (697, 885)}.get(lvl)
        merged_s = {0: (697, 885)}.get(lvl)
        ndoors = [y0 + 14 for y0, y1 in U_ROOMS if not (merged_n and merged_n[0] < y0 < merged_n[1])]
        sdoors = [y1 - 14 for y0, y1 in U_ROOMS if not (merged_s and merged_s[0] <= y0 < merged_s[1] - 100)]
        if lvl == 0:
            ndoors.append(966)
        interior_wall_y(250, iy0, iy1, zb, top, ndoors)
        interior_wall_y(216, iy0, iy1, zb, top, sdoors)
        for y in (695, 790, 885, 980):
            if not (merged_n and merged_n[0] < y < merged_n[1]):
                box(252, ix1, y, y + 2, zb, top, PLASTER)
            if not (merged_s and merged_s[0] < y < merged_s[1]):
                box(ix0, 216, y, y + 2, zb, top, PLASTER)
        recolor(250, 251, iy0, iy1, zb, zb + 9, PLASTER, DOOR_WOOD)
        recolor(217, 218, iy0, iy1, zb, zb + 9, PLASTER, DOOR_WOOD)
        for y in range(iy0 + 20, iy1, 60):
            box(232, 236, y - 4, y + 4, top - 1, top, LAMP)
        for i, y in enumerate((640, 830, 1010)):
            place(bulletin_board(16, 10, 200 + lvl * 10 + i), 249, y, zb + 12, '-x')
    stairs_y(995, (120, 140), UL[0], UL[1], +1)
    stairs_y(1055, (146, 166), UL[1], UL[2], -1)
    stairs_y(995, (120, 140), UL[2], UL[3], +1)


def north_room(i, lvl, span=None):
    y0, y1 = span or U_ROOMS[i]
    return Room(252, UX1 - 3, y0, y1, UL[lvl], '-x')


def south_room(i, lvl, span=None):
    y0, y1 = span or U_ROOMS[i]
    return Room(UX0 + 3, 216, y0, y1, UL[lvl], '+x')


def lounge(rm, seed=0):
    rm.put(rug(min(70, rm.w - 20), 46, RUG_BLUE), 10, 20)
    rm.put(tv(24), 0, 30, '+x', dz=10)
    rm.put(sofa(24, SOFA_GREEN), 30, 30, '-x')
    rm.put(coffee_table(), 18, 37, '+x')
    rm.put(sofa(20, SOFA_BROWN), 50, 4, '+y')
    rm.put(coffee_table(), 55, 17)
    rm.put(sofa(20, SOFA_BROWN), 50, 26, '-y')
    if rm.w > 150:
        rm.put(ping_pong(), 110, 20)
        rm.put(armchair(SOFA_GREEN), 150, 60, '+x')
        rm.put(armchair(SOFA_GREEN), 166, 60, '-x')
    rm.put(bookshelf(12, 20, seed), rm.w - 3, 50, '-x')
    for u, v in ((2, 2), (rm.w - 6, 2)):
        rm.put(plant(12), u, v)


def mailroom(rm):
    rm.put(mailboxes(80, 24), 0, 8, '+x')
    rm.put(counter(40, 7), 45, 20, '-x')
    rm.put(bookshelf(12, 20, 3, METAL_GRAY, (BOOK_TAN, DOOR_WOOD, BENCH_WOOD)), 60, 30, '-x')
    rm.put(bench(16), 20, rm.d - 12, '-y')
    rm.put(plant(12), rm.w - 6, 2)


def game_room(rm):
    rm.put(pool_table(), (rm.w - 25) // 2, 30)
    for u in (4, 13, 22):
        rm.put(arcade(), u, 0, '+y')
    rm.put(sofa(20, SOFA_GREEN), rm.w - 26, 70, '-y')


def newsroom(rm, seed=0):
    office(rm, 2, seed, CARPET2)
    rm.put(table(24, 10, BENCH_WOOD, METAL_DARK), rm.w // 2 - 12, rm.d // 2 + 6)
    for u in range(rm.w // 2 - 10, rm.w // 2 + 10, 4):
        rm.put([(0, 3, 0, 4, 0, 1, PLASTER)], u, rm.d // 2 + 9, dz=8)


def dining_hall(rm):
    """The Table at Higgins."""
    for u in (10, 54, 98, 232):
        for v in (6, 32):
            rm.put(dining_table(36), u, v)
    rm.put(serving_line(90), 120, 82)
    rm.put(plant(12), 2, 2)
    rm.put(plant(12), rm.w - 6, 2)


def kitchen(rm):
    rm.put(counter(80, 7, STEEL, STEEL), 6, 0, '+y')
    for u in (96, 106, 116):
        rm.put(stove(), u, 0, '+y')
    for v in (20, 30, 40, 50):
        rm.put(fridge(), rm.w - 8, v, '-x')
    rm.put(table(40, 12, STEEL, STEEL, 8), 30, 40)
    rm.put(table(40, 12, STEEL, STEEL, 8), 90, 40)
    rm.put(counter(60, 7, STEEL, STEEL), 20, rm.d - 16, '-y')


def cafe_lounge(rm):
    for u in range(8, rm.w - 22, 26):
        for v in (8, 34, 60):
            rm.put(cafe_set(CHAIR_RED if (u + v) % 2 else CHAIR_BLUE), u, v)
    rm.put(plant(12), 2, 2)


def tilton_ground(z):
    """Lobby with the information desk and the Bistro."""
    disc(305, T_DOOR, 18, z, z + 1, RUG_RED)
    c_letter(305, T_DOOR, z, 7, 12, WHITEBOARD, open_angle=math.pi / 2)
    place(counter(40, 7, DOOR_WOOD, GRANITE), 252, T_DOOR - 20, z, '+x')
    place(office_chair(), 243, T_DOOR - 12, z, '+x')
    place(office_chair(), 243, T_DOOR + 4, z, '+x')
    # the Bistro along the Main Street windows
    place(counter(70, 8, DOOR_WOOD, GRANITE), 130, 380, z, '-y')
    box(136, 144, 382, 386, z + 11, z + 17, STEEL)                    # espresso machine
    box(156, 176, 382, 387, z + 11, z + 16, GLASS)                    # pastry case
    box(157, 175, 383, 386, z + 11, z + 15, 0)
    box(158, 174, 384, 385, z + 11, z + 12, BOOK_TAN)
    box(126, 204, 398, 400, z, z + 30, WALL_CREAM)                   # back wall
    box(130, 200, 397, 398, z + 16, z + 28, BLACK_PLASTIC)            # menu board
    for zz in (z + 25, z + 22, z + 19):
        box(134, 190, 396, 397, zz, zz + 1, PLASTER)
    for x in range(132, 198, 8):
        place(stool(CHAIR_RED, 7), x, 372, z)
    for x in (110, 140, 170, 200, 230, 262):
        for y in (310, 336):
            place(cafe_set(CHAIR_RED if (x // 30 + y) % 2 else CHAIR_BLUE), x, y, z)
    for y in (520, 545):
        place(sofa(20, SOFA_GREEN), 336, y - 10, z, '-x')
    for x, y in ((95, 305), (350, 305), (95, 590), (350, 590)):
        place(plant(12), x, y, z)


def great_room(z):
    """Tilton Hall: stage, grand piano, granite fireplace, banquet tables."""
    box(130, 320, TY0 + 3, 343, z, z + 6, FLOOR_WOOD)
    box(130, 320, 342, 343, z, z + 6, DOOR_WOOD)
    box(215, 235, 343, 347, z, z + 3, FLOOR_WOOD)
    place(grand_piano(), 150, 318, z + 6, '+y')
    place(podium(), 222, 330, z + 6, '+y')
    cy = 450
    box(TX0 + 3, TX0 + 12, cy - 22, cy + 22, z, z + 36, GRANITE)
    box(TX0 + 6, TX0 + 12, cy - 12, cy + 12, z, z + 20, 0)
    box(TX0 + 3, TX0 + 6, cy - 12, cy + 12, z, z + 20, GRANITE_TEXT)
    box(TX0 + 7, TX0 + 10, cy - 8, cy + 8, z, z + 2, TRUNK)
    box(TX0 + 3, TX0 + 15, cy - 26, cy + 26, z + 22, z + 25, GRANITE_DARK)
    box(TX0 + 3, TX0 + 9, cy - 18, cy + 18, z + 36, 120, GRANITE)
    box(TX0 + 12, TX0 + 20, cy - 18, cy + 18, z, z + 1, GRANITE_DARK)
    for x in (160, 210, 260, 310):
        for y in (395, 450, 505):
            round_table(x, y, z)
    xc = (TX0 + TX1) / 2.0
    for x in (165, 285):
        for y in (420, 530):
            zv = int(-104 + math.sqrt(260 ** 2 - (x + 0.5 - xc) ** 2))
            box(x, x + 1, y, y + 1, 118, zv, METAL_DARK)
            disc(x + 0.5, y + 0.5, 6, 116, 117, BRONZE_LIGHT)
            box(x - 1, x + 2, y - 1, y + 2, 112, 116, LAMP)
            for a in range(8):
                px = x + 0.5 + 5.5 * math.cos(a * math.pi / 4)
                py = y + 0.5 + 5.5 * math.sin(a * math.pi / 4)
                box(int(px), int(px) + 1, int(py), int(py) + 1, 117, 119, LAMP)
    for y in (360, 560):
        place(painting(14, 18, 'portrait'), TX0 + 3, y - 7, z + 24, '+x')
    for x in (150, 300):
        place(painting(18, 14, 'landscape'), x, TY1 - 4, z + 26, '-y')


def furnish_uc():
    z0, z1, z2, z3 = UL[:4]
    tilton_ground(z0)
    great_room(z1)
    lounge(north_room(0, 0), 1)
    dining_hall(north_room(0, 0, (697, 980)))
    cafe_lounge(north_room(4, 0))
    storage(south_room(0, 0), 41)
    kitchen(south_room(0, 0, (697, 885)))
    storage(south_room(3, 0), 42)
    mailroom(north_room(0, 1))
    lounge(north_room(0, 1, (697, 885)), 2)
    meeting_room(north_room(3, 1), 110)
    meeting_room(north_room(4, 1), 111)
    office(south_room(0, 1), 1, 112)
    meeting_room(south_room(1, 1), 113)
    meeting_room(south_room(2, 1), 114)
    office(south_room(3, 1), 1, 115)
    office(north_room(0, 2), 2, 120, RUG_RED)                 # student government
    meeting_room(north_room(1, 2), 121, CHAIR_RED)
    meeting_room(north_room(2, 2), 122, CHAIR_BLUE)
    game_room(north_room(3, 2))
    newsroom(north_room(4, 2), 123)                           # The Scarlet
    for i in range(4):
        office(south_room(i, 2), 1 + i % 2, 130 + i)
    for i in range(5):
        office(north_room(i, 3), 1 + i % 2, 140 + i, (RUG_BLUE, CARPET2, RUG_RED)[i % 3])
    for i in range(4):
        office(south_room(i, 3), 1, 150 + i, CARPET2)
    for lvl in range(4):
        ceil = UL[lvl + 1] - 2
        for y0, y1 in U_ROOMS:
            ceiling_lights(252, UX1 - 3, y0, y1, ceil, 2)
            ceiling_lights(UX0 + 3, 216, y0, y1, ceil, 2)
    ceiling_lights(TX0 + 3, TX1 - 3, TY0 + 3, TY1 - 3, UL[1] - 2, 4)


# --------------------------------------------------------------------------
# Main Street, the entrance and the Green
# --------------------------------------------------------------------------
def street_lamp(x, y, toward):
    box(x - 1, x + 3, y - 1, y + 3, 2, 6, METAL_DARK)
    box(x, x + 2, y, y + 2, 2, 82, METAL_DARK)
    ye = y + toward * 26
    box(x, x + 2, min(y, ye), max(y, ye) + 2, 80, 82, METAL_DARK)
    box(x - 2, x + 4, ye - 3, ye + 5, 76, 80, METAL_GRAY)
    box(x - 1, x + 3, ye - 2, ye + 4, 75, 76, LAMP)


def main_street():
    box(0, NX, 0, ROAD0 - 2, 0, 2, CONCRETE)                  # far sidewalk
    box(0, NX, ROAD0 - 2, ROAD0, 0, 2, GRANITE)
    box(0, NX, ROAD0, ROAD1, 0, 1, ASPHALT)
    box(0, NX, ROAD1, ROAD1 + 2, 0, 2, GRANITE)
    box(0, NX, ROAD1 + 2, PROP, 0, 2, CONCRETE)               # near sidewalk
    for x in range(0, NX, 15):
        box(x, x + 1, 0, ROAD0 - 2, 1, 2, CONCRETE2)
        box(x, x + 1, ROAD1 + 2, PROP, 1, 2, CONCRETE2)
    box(0, NX, 175, 176, 0, 1, PAINT_WHITE)                   # bus / bike lane
    box(0, NX, 140, 141, 0, 1, PAINT_YELLOW)                  # double yellow
    box(0, NX, 137, 138, 0, 1, PAINT_YELLOW)
    for x in range(0, NX, 40):
        box(x, x + 20, 103, 104, 0, 1, PAINT_WHITE)           # lane line
    box(0, NX, 68, 69, 0, 1, PAINT_WHITE)                     # bike lane
    for x in (300, 1150):
        draw_text_flat("BUS", x, 200, 0, PAINT_WHITE, 3)
    for x in range(160, NX, 420):
        for dx, dy in ((0, 0), (8, 0)):
            disc(x + dx, 55 + dy, 3, 0, 1, PAINT_WHITE)
            disc(x + dx, 55 + dy, 1.6, 0, 1, ASPHALT)
        box(x, x + 9, 55, 56, 0, 1, PAINT_WHITE)
    # crosswalk to the main gate (brick red with white edges), curb extension
    box(727, 757, ROAD0, ROAD1, 0, 1, CROSSWALK)
    box(725, 727, ROAD0, ROAD1, 0, 1, PAINT_WHITE)
    box(757, 759, ROAD0, ROAD1, 0, 1, PAINT_WHITE)
    box(700, 785, 176, ROAD1 + 2, 0, 2, CONCRETE)
    box(700, 785, 176, 178, 0, 2, GRANITE)
    box(727, 757, 176, 192, 1, 2, 0)
    for x in range(120, NX, 300):
        disc(x, 120, 3.5, 0, 1, METAL_DARK)                   # manholes
    for x in range(200, NX, 400):
        box(x, x + 8, 206, 210, 0, 1, METAL_DARK)
        box(x, x + 8, 40, 44, 0, 1, METAL_DARK)
    for x in (120, 370, 610, 890, 1140, 1390):
        street_lamp(x, 214, -1)
    for x in (250, 750, 1250):
        street_lamp(x, 20, +1)
    disc(330.5, 220.5, 2.2, 2, 9, HYDRANT_RED)
    disc(330.5, 220.5, 1.6, 9, 11, HYDRANT_RED)
    box(326, 335, 220, 221, 6, 8, HYDRANT_RED)
    box(560, 566, 222, 227, 3, 13, MAILBOX_BLUE)
    box(560, 566, 223, 226, 13, 14, MAILBOX_BLUE)
    box(561, 565, 221, 222, 10, 11, METAL_DARK)
    for a, b in ((560, 222), (565, 222), (560, 226), (565, 226)):
        box(a, a + 1, b, b + 1, 2, 3, METAL_DARK)
    # bus stop shelter
    box(450, 522, 245, 247, 2, 26, GLASS)
    box(450, 452, 230, 247, 2, 26, GLASS)
    box(520, 522, 230, 247, 2, 26, GLASS)
    for x in (450, 486, 520):
        box(x, x + 2, 245, 247, 2, 26, METAL_DARK)
    box(448, 524, 228, 249, 26, 28, METAL_GRAY)
    place(bench(30), 470, 238, 2, '-y')
    box(532, 533, 216, 217, 2, 28, METAL_DARK)
    box(530, 535, 216, 217, 22, 28, CHAIR_RED)
    box(531, 534, 215, 216, 24, 26, WHITEBOARD)


def entrance_and_gate():
    """Red-brick entrance plaza at the sidewalk with the "C" gate."""
    x0, x1, y1 = 620, 865, 325
    pavers(x0, x1, PROP, y1)
    for cx in (x0 + 30, x1 - 30):                              # rounded inner corners
        for x in range(cx - 30, cx + 31):
            for y in range(y1 - 30, y1):
                if (x < x0 + 30 or x >= x1 - 30) and math.hypot(x + 0.5 - cx, y + 0.5 - (y1 - 30)) > 30:
                    if x0 <= x < x1:
                        G[x, y, 0] = GRASS
    for bx0, bx1 in ((560, 620), (865, 925)):                 # planting beds
        box(bx0, bx1, PROP, 292, 0, 1, MULCH)
        box(bx0, bx1, 292, 293, 1, 2, GRANITE_DARK)
    gy = 322
    for px in (712, 760):
        box(px, px + 12, gy - 6, gy + 6, 0, 30, BRICK)
        box(px - 1, px + 13, gy - 7, gy + 7, 30, 33, GRANITE)
        ball(px + 6, gy + 0.5, 37, 3.2, GRANITE)
    for x in range(724, 760):
        t = (x + 0.5 - 724) / 36.0
        za = 30 + int(round(9 * math.sin(math.pi * t)))
        box(x, x + 1, gy - 1, gy + 1, za, za + 2, METAL_DARK)
        if (x - 724) % 4 == 2:
            box(x, x + 1, gy, gy + 1, 27, za, METAL_DARK)
    box(724, 760, gy, gy + 1, 27, 28, METAL_DARK)
    for x in range(AXIS - 9, AXIS + 10):
        for z in range(37, 56):
            if 7 <= math.hypot(x + 0.5 - AXIS, z + 0.5 - 47) < 8.4:
                box(x, x + 1, gy - 1, gy + 1, z, z + 1, METAL_DARK)
    c_letter(AXIS, 47, 0, 3.6, 6.2, BRONZE_LIGHT, plane='xz', y_plane=(gy - 1, gy + 1))


def ground():
    G[:, PROP:, 0] = GRASS
    # walks (concrete, like the real ones)
    thick_line(660, 318, 368, T_DOOR, 22, 0, CONCRETE)          # gate -> Tilton Hall door
    thick_line(368, T_DOOR + 10, AXIS, 545, 22, 0, CONCRETE)    # cross walk
    thick_line(AXIS, 532, 900, 548, 18, 0, CONCRETE)            # spur to the sitting circle
    disc(915, 585, 30, 0, 1, CONCRETE)
    disc(915, 585, 22, 0, 1, GRASS)
    thick_line(AXIS, 335, 950, 352, 20, 0, CONCRETE)            # walk along Main Street
    thick_line(642, 826, 374, (VEST[0] + VEST[1]) // 2, 22, 0, CONCRETE)   # plaza -> UC entrance
    thick_line(842, 868, 1030, 930, 22, 0, CONCRETE)            # plaza -> north end of JCH
    box(730, 754, 325, 783, 0, 1, CONCRETE)                      # main walk
    box(TX1 + 8, TX1 + 30, TY0, TY1, 0, 1, CONCRETE)             # along the Tilton / UC facades
    box(TX1, TX1 + 8, TY0, TY1, 0, 1, MULCH)
    box(TX1, TX1 + 30, T_DOOR - 16, T_DOOR + 16, 0, 1, CONCRETE)
    box(UX1, UX1 + 46, UY0, UY1, 0, 1, CONCRETE)
    box(UX1, JX0, 985, 1240, 0, 1, CONCRETE)                     # between UC and JCH
    box(UX1, 1080, JY1, 1240, 0, 1, CONCRETE)                    # behind JCH
    box(JX1, 1080, 930, JY1, 0, 1, CONCRETE)
    box(JX0, JX1, 988, JY0 - 12, 0, 1, MULCH)                    # planting strip along the facade
    # Red Square: granite slabs with a red brick square in the middle
    for x in range(642, 842):
        for y in range(783, 870):
            joint = (x - 642) % 25 == 0 or (y - 783) % 25 == 0
            G[x, y, 0] = GRANITE_DARK if joint else GRANITE
    pavers(712, 772, 796, 856)
    for x in range(726, 758):                                    # walk up to the door
        for y in range(870, JY0 - 10):
            G[x, y, 0] = GRANITE_DARK if (y - 870) % 25 == 0 else GRANITE
    # planting beds either side of the entrance walk
    for bx0, bx1, by0 in ((762, 1030, 900), (595, 722, 930)):
        box(bx0, bx1, by0, 987, 0, 1, MULCH)
        box(bx0, bx1, by0, by0 + 1, 1, 2, GRANITE_DARK)
        box(bx0, bx0 + 1, by0, 987, 1, 2, GRANITE_DARK)
        box(bx1 - 1, bx1, by0, 987, 1, 2, GRANITE_DARK)


def lawn_lamp(x, y):
    box(x, x + 2, y, y + 2, 1, 38, METAL_DARK)
    box(x - 1, x + 3, y - 1, y + 3, 1, 3, METAL_DARK)
    box(x - 1, x + 3, y - 1, y + 3, 38, 43, LAMP)
    box(x - 2, x + 4, y - 2, y + 4, 43, 44, METAL_DARK)


def landscape():
    for y in (380, 470, 620, 720):
        lawn_lamp(722, y)
        lawn_lamp(760, y)
    for x, y in ((636, 778), (846, 778), (636, 872), (846, 872), (690, 300), (795, 300),
                 (380, 700), (380, 960), (1060, 940)):
        lawn_lamp(x, y)
    for y in (430, 660):
        place(bench(16), 712, y, 1, '+x')
        place(bench(16), 763, y, 1, '-x')
        place(trash_can(), 714, y + 18, 1)
    for y in (800, 840):                                         # benches round Red Square
        place(bench(16), 644, y, 1, '+x')
        place(bench(16), 835, y, 1, '-x')
    for a in (0.6, 2.0, 3.4):                                    # sitting circle
        x, y = 915 + 24 * math.cos(a), 585 + 24 * math.sin(a)
        place(bench(14), int(x) - 7, int(y) - 3, 1, '+y' if math.sin(a) > 0.5 else '-x')
    for i in range(5):                                           # bike racks at the UC
        y = 945 + 6 * i
        box(UX1 + 4, UX1 + 5, y, y + 1, 1, 9, METAL_GRAY)
        box(UX1 + 10, UX1 + 11, y, y + 1, 1, 9, METAL_GRAY)
        box(UX1 + 4, UX1 + 11, y, y + 1, 8, 9, METAL_GRAY)
    r = np.random.default_rng(5)
    for bx0, bx1, by0 in ((762, 1030, 900), (595, 722, 930)):    # shrubs in the beds
        for x in range(bx0 + 8, bx1 - 6, 16):
            for y in range(by0 + 10, 980, 26):
                if r.random() < 0.7:
                    leaf_blob(x + r.uniform(-3, 3), y, 4, 6, 6, 5, (SHRUB, SHRUB2), r, 0.9, 6)
    for bx0, bx1 in ((560, 620), (865, 925)):
        for x in range(bx0 + 6, bx1 - 4, 13):
            leaf_blob(x, 270, 4, 6, 6, 5, (SHRUB, SHRUB2), r, 0.9, 6)
    for y in range(TY0 + 15, TY1 - 10, 22):                      # along the UC facades
        if abs(y - T_DOOR) > 25:
            leaf_blob(TX1 + 4, y, 4, 4, 7, 5, (SHRUB, SHRUB2), r, 0.9, 6)
    for x in range(JX0 + 10, JX1 - 10, 18):                      # along Jonas Clark Hall
        if not (680 < x < 805):
            leaf_blob(x, JY0 - 17, 4, 6, 5, 5, (SHRUB, SHRUB2), r, 0.9, 6)


# --------------------------------------------------------------------------
# Sigmund Freud statue: bronze Freud on a low wall at Red Square, reading
# --------------------------------------------------------------------------
FREUD_X, FREUD_Y, WALL_Y1 = 690, 775, 783


def freud_statue():
    S = 1.8                     # statue is slightly larger than life
    seat_z = 10                 # wall top
    for x0, x1 in ((652, 726), (758, 832)):
        box(x0, x1, FREUD_Y, WALL_Y1, 1, seat_z - 1, GRANITE)
        box(x0 - 1, x1 + 1, FREUD_Y - 1, WALL_Y1 + 1, seat_z - 1, seat_z, GRANITE_DARK)

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
    box(FREUD_X + 11, FREUD_X + 21, FREUD_Y - 1, FREUD_Y, 3, 7, BRONZE_DARK)   # plaque


# --------------------------------------------------------------------------
# Trees, placed after the aerial photos: big oaks and maples on the Green,
# small ornamental trees in the beds in front of Jonas Clark Hall
# --------------------------------------------------------------------------
TREES = [
    # (kind, x, y, crown)
    ('oak', 506, 880, 104), ('maple', 628, 672, 82), ('small', 642, 396, 30),
    ('oak', 527, 322, 100), ('maple', 788, 437, 82), ('oak', 836, 760, 112),
    ('maple', 911, 860, 96), ('oak', 1133, 854, 110), ('oak', 1039, 695, 100),
    ('maple', 988, 537, 94), ('maple', 975, 410, 70), ('oak', 1105, 312, 100),
    ('oak', 455, 285, 92), ('oak', 1250, 1150, 96), ('maple', 1290, 560, 80),
    ('small', 800, 945, 26), ('small', 880, 955, 26), ('red', 985, 948, 26),
    ('small', 655, 958, 24),
]


def plant_trees():
    for i, (kind, x, y, crown) in enumerate(TREES):
        seed = 3000 + i
        if kind == 'oak':
            deciduous(x, y, 215, crown, 4.6, (LEAF, LEAF2, LEAF2, LEAF3), seed, 0.46)
        elif kind == 'maple':
            deciduous(x, y, 190, crown, 3.8, (LEAF, LEAF3, LEAF3, LEAF2), seed, 0.46)
        elif kind == 'red':
            deciduous(x, y, 62, crown, 1.8, (RED_LEAF, RED_LEAF2), seed, 0.6, mulch=0)
        else:
            deciduous(x, y, 66, crown, 1.9, (LEAF3, LOCUST), seed, 0.58, mulch=0)


def check_trees():
    found = np.isin(G, TREE_SET + [0], invert=True)
    for kind, x, y, crown in TREES:
        r = int(crown * 0.7)
        if found[max(0, x - r):x + r, max(0, y - r):y + r, 60:220].any():
            print('note: crown of %s tree at (%d, %d) touches a structure' % (kind, x, y))


# --------------------------------------------------------------------------
# Build and export
# --------------------------------------------------------------------------
def build():
    ground()
    main_street()
    entrance_and_gate()
    jonas_clark_hall()
    jch_structure()
    furnish_jch()
    tilton_building()
    uc_building()
    tilton_structure()
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
    vary(ASPHALT, (ASPHALT2,), (0.3,))


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

    # Ground: dirt over hard masonry, larger than the map so a small pivot
    # difference can never leave a gap.  Voxbox tiles are <= 256.
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

    sx, sy, sz = to_td(AXIS, 232, 3)       # on the sidewalk in front of the gate
    xml = '\n'.join([
        '<scene version="6" shadowVolume="150 50 140">',
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
                'description = Clark University, Worcester MA, laid out after aerial photos: '
                'Main Street and the "C" gate, the Green with its big trees, Red Square with the '
                'seated Sigmund Freud statue, Jonas Clark Hall (1887) and the Higgins University '
                'Center with Tilton Hall, all with furnished interiors. Everything is destructible.\n'
                'tags = Map\n')
    return len(lines), total


VIEWS = {
    # name: (x range, y range, z range) of the grid to render
    'entrance_gate': ((600, 890), (160, 420), (0, 90)),
    'jonas_clark_hall': ((400, 1090), (740, 1280), (0, 256)),
    'red_square_freud': ((630, 860), (740, 900), (0, 60)),
    'university_center': ((0, 420), (240, 1120), (0, 256)),
    'jch_ground_floor': ((427, 1058), (JY0 + 3, 1215), (0, JL[1] - 2)),
    'jch_third_floor': ((427, 1058), (JY0 + 3, 1215), (0, JL[3] - 2)),
    'uc_ground_floor': ((80, 380), (290, 1090), (0, UL[1] - 2)),
    'tilton_great_room': ((85, 365), (295, 605), (0, 100)),
    'uc_second_floor': ((105, 380), (595, 1090), (0, UL[2] - 2)),
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
