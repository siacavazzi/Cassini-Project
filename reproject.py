# -*- coding: utf-8 -*-
"""
Moves the target's surface in an older frame to where it is in a newer frame.

Frames in a rolling mosaic are taken minutes apart and the target keeps rotating (Jupiter
turns about 3.5 degrees in 7 minutes), so centering every frame on the target is not
enough: cloud features in an older panel no longer line up with the newest one. Here every
pixel of the newest frame that lands on the target is traced to a point on the target's
surface (an ellipsoid), and that point is looked up in the older frame at the older frame's
time. Pixels off the target (space, rings) keep the plain centered placement.

The lighting stays where the sun puts it, so moved clouds are re-lit for the newer frame
(see brightness).

Each frame needs two things, which find_target and label.translate record on the label:
* geometry: time, camera, target, and the camera model below
* placement: 3x3 matrix from a pixel of the image to its pixel on the output canvas

Camera model (the pinhole model find_target uses): a pixel at (col, row) of the 1024 pixel
image looks along (u, v, 1) in the camera frame, with
    col = center - u * scale
    row = center - v * scale
"""
import numpy as np
import cv2


minnaert_k = 0.9     # limb darkening (Minnaert exponent); 1 is a plain Lambert surface
grid_step = 4       # the pixel map is worked out every grid_step pixels and interpolated in between
max_relight = 1.5   # most the lighting correction may brighten or darken a moved pixel
margin = 0.15       # how far (fraction of the frame's size) surface features may move between frames


"""
Looks up, with SPICE, everything about one frame that doesn't depend on the pixel:
  cam_to_body  rotation from the camera frame to the target's body-fixed frame
  observer     spacecraft position in the body-fixed frame (km)
  radii        target's ellipsoid radii (km)
  sun          unit vector towards the sun in the body-fixed frame
Returns None if SPICE doesn't know the target's shape or orientation.
"""
def spice_view(geometry):
    import spiceypy as sp
    try:
        target = geometry["target"]
        et = geometry["et"]
        state, lt = sp.spkezr(target, et, "J2000", "LT+S", "CASSINI")
        # the target's orientation when the light left it
        j2000_to_body = np.array(sp.pxform("J2000", f"IAU_{target}", et - lt))
        cam_to_j2000 = np.array(sp.pxform(geometry["camera"], "J2000", et))
        radii = np.array(sp.bodvrd(target, "RADII", 3)[1])
        # direction to the sun from the target, when the light left the target
        sun = np.array(sp.spkpos("SUN", et - lt, "J2000", "LT+S", target)[0])
    except Exception as e:
        print(f"No surface geometry for {geometry.get('target')}: {e}")
        return None
    return {
        "cam_to_body": j2000_to_body @ cam_to_j2000,
        "observer": j2000_to_body @ -np.array(state[:3]),
        "radii": radii,
        "sun": j2000_to_body @ (sun / np.linalg.norm(sun)),
    }


def pixel_to_ray(geometry, col, row):
    c, scale = geometry["center"], geometry["scale"]
    u = (c - col) / scale
    v = (c - row) / scale
    return np.stack([u, v, np.ones_like(u)], axis=-1)


def ray_to_pixel(geometry, ray):
    c, scale = geometry["center"], geometry["scale"]
    col = c - ray[..., 0] / ray[..., 2] * scale
    row = c - ray[..., 1] / ray[..., 2] * scale
    return col, row


def apply(matrix, x, y):
    return (matrix[0, 0] * x + matrix[0, 1] * y + matrix[0, 2],
            matrix[1, 0] * x + matrix[1, 1] * y + matrix[1, 2])


"""
Where the rays through canvas points (x, y) of a frame hit the target's surface.
Returns body-fixed points (km) and a mask of the rays that hit.
"""
def surface_points(geometry, view, placement, x, y):
    col, row = apply(np.linalg.inv(placement), x, y)
    ray = pixel_to_ray(geometry, col, row) @ view["cam_to_body"].T
    # scale space so the ellipsoid becomes a unit sphere, then solve |o + t d| = 1
    o = view["observer"] / view["radii"]
    d = ray / view["radii"]
    a = (d * d).sum(-1)
    b = 2 * (d @ o)
    c = o @ o - 1
    disc = b * b - 4 * a * c
    hit = disc >= 0
    t = (-b - np.sqrt(np.where(hit, disc, 0))) / (2 * a)
    hit &= t > 0
    return view["observer"] + t[..., None] * ray, hit


"""
Where body-fixed surface points appear on a frame's canvas. Points on the far side of the
target as seen by that frame are marked not visible.
"""
def canvas_points(geometry, view, placement, points):
    to_point = points - view["observer"]
    normal = points / view["radii"] ** 2
    visible = (normal * to_point).sum(-1) < 0
    ray = to_point @ view["cam_to_body"]   # body-fixed -> camera frame
    visible &= ray[..., 2] > 0
    col, row = ray_to_pixel(geometry, ray)
    x, y = apply(placement, col, row)
    return x, y, visible


"""
How bright a surface point looks from a frame for a given albedo (Minnaert model):
mu0^k * mu^(k - 1), with mu0 / mu the cosines of the sun's and the camera's angle
from the surface normal. Moving clouds from one frame to another keeps their albedo but
changes their lighting, so the brightness is scaled by the ratio of the two.
"""
def brightness(view, points):
    normal = points / view["radii"] ** 2
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    to_camera = view["observer"] - points
    to_camera /= np.linalg.norm(to_camera, axis=-1, keepdims=True)
    mu0 = np.clip(normal @ view["sun"], 0, 1)
    mu = np.clip((normal * to_camera).sum(-1), 1e-3, 1)
    return mu0 ** minnaert_k * mu ** (minnaert_k - 1), mu0


"""
Redraws an older frame's canvas so its view of the target's surface matches the newest
frame. old/new = (canvas image, geometry, view, placement); views come from spice_view.
Returns the redrawn canvas (same size, RGBA).
"""
def warp_to_newest(old, new):
    image, g_old, v_old, p_old = old
    _, g_new, v_new, p_new = new
    h, w = image.shape[:2]

    ys, xs = np.nonzero(image[::8, ::8, 3])
    if len(ys) == 0:
        return image
    pad = int(margin * max(np.ptp(ys), np.ptp(xs)) * 8) + 16
    y0, y1 = max(ys.min() * 8 - pad, 0), min(ys.max() * 8 + pad, h)
    x0, x1 = max(xs.min() * 8 - pad, 0), min(xs.max() * 8 + pad, w)

    # work out the map on a coarse grid of output pixels
    gy = np.arange(y0, y1 + grid_step, grid_step, dtype=np.float64)
    gx = np.arange(x0, x1 + grid_step, grid_step, dtype=np.float64)
    gx, gy = np.meshgrid(gx, gy)
    points, hit = surface_points(g_new, v_new, p_new, gx, gy)
    sx, sy, visible = canvas_points(g_old, v_old, p_old, points)
    # off the target the frame stays where it was (no shift). Where the older frame has
    # nothing to show (out of its sight, or in its dark), the centered frame is kept too.
    drawn = hit & visible
    gain = np.ones(gx.shape, np.float32)
    fade = np.ones(gx.shape, np.float32)
    if "sun" in v_old and "sun" in v_new:
        b_new, mu0_new = brightness(v_new, points)
        b_old, mu0_old = brightness(v_old, points)
        # past the terminator the visible edge of the planet sits well inside the
        # ellipsoid's limb, so moved pixels there land on dark sky: keep the centered
        # pixels, and fade the moved ones in gradually as the sun rises
        lit = np.minimum(mu0_new, mu0_old)
        drawn &= lit > 0.05
        fade = np.clip((lit - 0.05) / 0.10, 0, 1).astype(np.float32)
        ratio = np.where(b_old > 1e-6, b_new / np.maximum(b_old, 1e-6), 1.0)
        # near the limb and terminator the lighting model is least reliable: only correct
        # a little, and not at all where the sun or camera is near grazing
        steady = np.clip((np.minimum(mu0_new, mu0_old) - 0.05) / 0.15, 0, 1)
        ratio = 1 + (np.clip(ratio, 1 / max_relight, max_relight) - 1) * steady
        gain = np.where(drawn, ratio, 1.0).astype(np.float32)
    shift_x = np.where(drawn, sx - gx, 0).astype(np.float32)
    shift_y = np.where(drawn, sy - gy, 0).astype(np.float32)
    weight = np.where(drawn, fade, 0).astype(np.float32)

    # fill in between the grid points. Interpolating the shift (not the map itself) keeps
    # the off-target pixels exactly where they were.
    fine_y = (np.arange(y0, y1) - y0) / grid_step
    fine_x = (np.arange(x0, x1) - x0) / grid_step
    fx, fy = np.meshgrid(fine_x.astype(np.float32), fine_y.astype(np.float32))
    fine = lambda a: cv2.remap(a, fx, fy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    shift_x, shift_y, gain = fine(shift_x), fine(shift_y), fine(gain)
    # soften the edge between moved and centered pixels over a few grid steps, so the
    # limb doesn't show the grid's staircase
    weight = cv2.GaussianBlur(fine(weight), (0, 0), grid_step)
    px, py = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))

    centered = image[y0:y1, x0:x1].astype(np.float32)
    warped = cv2.remap(image, px + shift_x, py + shift_y, cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0)).astype(np.float32)
    warped[..., :3] *= gain[..., None]
    w = weight[..., None]
    out = np.zeros_like(image)
    out[y0:y1, x0:x1] = np.clip(warped * w + centered * (1 - w), 0, 255).round()
    return out


"""
Surface reprojection for pictures put north up on the body's centre by SPICE (the camera windows' mosaic tiles,
obs_mosaic): there a picture's pixel is a place on the sky round the body's centre, x = -east and y = -north on the
sky plane at the body (celestial north up, east to the left as on the sky), in reference pixels of km_px km. A
mosaic's panels are taken minutes apart and the body turns, and Cassini moves, in between, so the surface under one
place on the sky moves between panels by 8 to 18 px on the moons (measured, panel_probe / panel_motion) while the
body's centre stays put. sky_field works out, for a picture taken at et, where each place on the sky at another
time (the mosaic's epoch) shows that surface point in the picture, so the picture can be redrawn as at the epoch.
"""
def sky_view(target, et):
    """The geometry of target from Cassini at et: (centre vector from Cassini, unit line of sight, sky north, sky
    east (J2000), J2000 to body-fixed rotation, radii, sun direction body-fixed)."""
    import spiceypy as sp
    pos, lt = sp.spkpos(target, et, "J2000", "LT+S", "CASSINI")
    c = np.array(pos)
    ch = c / np.linalg.norm(c)
    north = np.array([0.0, 0.0, 1.0]) - ch[2] * ch
    north /= np.linalg.norm(north)
    east = np.cross(north, ch)
    rot = np.array(sp.pxform("J2000", f"IAU_{target}", et - lt))
    radii = np.array(sp.bodvrd(target, "RADII", 3)[1])
    sun = np.array(sp.spkpos("SUN", et - lt, "J2000", "LT+S", target)[0])
    return {"c": c, "ch": ch, "north": north, "east": east, "rot": rot, "radii": radii,
            "sun": rot @ (sun / np.linalg.norm(sun))}


def sky_to_surface(view, x, y, km_px):
    """Body-fixed points (km) under sky places x, y (reference pixels from the body's centre), and which hit."""
    ray = (view["c"] + (-x * km_px)[..., None] * view["east"] + (-y * km_px)[..., None] * view["north"]) @ view["rot"].T
    o = view["rot"] @ -view["c"] / view["radii"]
    d = ray / view["radii"]
    a = (d * d).sum(-1)
    b = 2 * (d @ o)
    cc = o @ o - 1
    disc = b * b - 4 * a * cc
    hit = disc >= 0
    t = (-b - np.sqrt(np.where(hit, disc, 0))) / (2 * a)
    hit &= t > 0
    return view["rot"] @ -view["c"] + t[..., None] * ray, hit


def surface_to_sky(view, points, km_px):
    """Sky places (reference pixels from the body's centre) of body-fixed points, and which are on the near side."""
    observer = view["rot"] @ -view["c"]
    to_point = points - observer
    visible = ((points / view["radii"] ** 2) * to_point).sum(-1) < 0
    v = to_point @ view["rot"]   # body-fixed -> J2000 (Cassini to the point)
    d = np.linalg.norm(view["c"])
    sky = v * (d / (v @ view["ch"]))[..., None] - view["c"]
    return -(sky @ view["east"]) / km_px, -(sky @ view["north"]) / km_px, visible


LIMB_TAPER = 0.25         # the shift fades to none where the epoch sees the surface at a cosine below this (the limb)
TERMINATOR_TAPER = 0.15   # and where the sun is lower than this cosine (the terminator)


def sky_field(epoch, view, x, y, km_px):
    """For sky places x, y at the epoch's view: where the picture taken at view shows the same surface point (its
    shift dx, dy from x, y), and weight 1 on the body, 0 off it. The shift fades smoothly to none toward the limb and
    toward the terminator (as seen and lit at the epoch), so the picture's mapping stays continuous: the limb stays
    where SPICE drew it, one edge, with no sky looked up inside it, and the night side keeps its place instead of
    dragging dark ground over lit (round 4 of the panel probe: a dark band inside Rhea's limb, black patches at
    Dione's terminator). The few pixels of misregistration left in those bands are the panels step's to take up."""
    points, hit = sky_to_surface(epoch, x, y, km_px)
    sx, sy, _ = surface_to_sky(view, points, km_px)
    normal = points / epoch["radii"] ** 2
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    seen = epoch["rot"] @ -epoch["c"] - points
    mu = (normal * seen).sum(-1) / np.maximum(np.linalg.norm(seen, axis=-1), 1e-9)
    mu0 = normal @ epoch["sun"]
    k = np.clip(mu / LIMB_TAPER, 0, 1) * np.clip(mu0 / TERMINATOR_TAPER, 0, 1) * hit
    return ((sx - x) * k).astype(np.float32), ((sy - y) * k).astype(np.float32), hit.astype(np.float32)


def field_stretch(dx, dy, weight, step):
    """How much a field (sky_field, on a grid of step pixels) stretches or squeezes the picture it redraws: the
    largest change of its shift per pixel between neighboring grid points both on the body (0 for a shift the same
    everywhere; 1 squeezes a stretch of surface to nothing)."""
    on = weight > 0.5
    worst = 0.0
    for a in (dx, dy):
        for g, both in ((np.diff(a, axis=1), on[:, 1:] & on[:, :-1]), (np.diff(a, axis=0), on[1:] & on[:-1])):
            if both.any():
                worst = max(worst, float(np.abs(g[both]).max()) / step)
    return worst


def warp_sky(image, dx, dy, weight, step):
    """image (RGBA, its pixel (0, 0) at the field's grid point (0, 0)) redrawn as at the field's epoch: dx, dy,
    weight on a grid of step pixels (sky_field), filled in between; off the body (weight 0) it stays as it is (the
    shift fades to none at the limb, so the cells the limb crosses need nothing worked out pixel by pixel)."""
    h, w = image.shape[:2]
    fy, fx = np.meshgrid(np.arange(h, dtype=np.float32) / step, np.arange(w, dtype=np.float32) / step, indexing="ij")
    fine = lambda a: cv2.remap(a, fx, fy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    sx, sy, wt = fine(dx), fine(dy), fine(weight)
    px, py = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    # (Lanczos, as the tiles are resized: a linear lookup softened every crater rim)
    warped = cv2.remap(image, px + sx, py + sy, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT,
                       borderValue=(0, 0, 0, 0)).astype(np.float32)
    k = wt[..., None]
    return np.clip(warped * k + image.astype(np.float32) * (1 - k), 0, 255).round().astype(np.uint8)
