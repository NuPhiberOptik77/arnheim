"""Every surface, made from procedural shader nodes: no image textures, nothing downloaded.

Each function returns a material, built once and then reused by name. Colours are sRGB hex.
"""
import bpy

_cache = {}


def hex_rgb(h, a=1.0):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, a)


class G:
    """A tiny graph builder: G(mat).n('ShaderNodeTexNoise', Scale=4) makes a node and sets its inputs."""

    def __init__(self, mat):
        self.t = mat.node_tree
        self.t.nodes.clear()
        self.out = self.t.nodes.new("ShaderNodeOutputMaterial")
        self.bsdf = self.n("ShaderNodeBsdfPrincipled")
        self.link(self.bsdf, "BSDF", self.out, "Surface")

    def n(self, kind, **inputs):
        node = self.t.nodes.new(kind)
        for k, v in inputs.items():
            if k.startswith("_"):
                setattr(node, k[1:], v)
            else:
                node.inputs[k].default_value = v
        return node

    def link(self, a, out, b, inp):
        self.t.links.new(a.outputs[out] if isinstance(out, str) else a.outputs[out], b.inputs[inp] if isinstance(inp, str) else b.inputs[inp])

    def set(self, **inputs):
        for k, v in inputs.items():
            self.bsdf.inputs[k.replace("_", " ")].default_value = v

    def ramp(self, fac_node, fac_out, stops):
        r = self.n("ShaderNodeValToRGB")
        r.color_ramp.elements[0].position, r.color_ramp.elements[0].color = stops[0][0], hex_rgb(stops[0][1])
        r.color_ramp.elements[1].position, r.color_ramp.elements[1].color = stops[-1][0], hex_rgb(stops[-1][1])
        for pos, col in stops[1:-1]:
            e = r.color_ramp.elements.new(pos)
            e.color = hex_rgb(col)
        self.link(fac_node, fac_out, r, "Fac")
        return r

    def coords(self, kind="Object", scale=(1, 1, 1)):
        tc = self.n("ShaderNodeTexCoord")
        mp = self.n("ShaderNodeMapping", _vector_type="POINT")
        mp.inputs["Scale"].default_value = scale
        self.link(tc, kind, mp, "Vector")
        return mp

    def bump(self, height_node, out, strength, distance=0.01):
        b = self.n("ShaderNodeBump", Strength=strength, Distance=distance)
        self.link(height_node, out, b, "Height")
        self.link(b, "Normal", self.bsdf, "Normal")
        return b


def material(name):
    def deco(fn):
        def make(*args, **kw):
            key = name + (":" + ":".join(map(str, args)) if args else "") + (":" + ":".join(f"{k}={v}" for k, v in sorted(kw.items())) if kw else "")
            if key in _cache:
                return _cache[key]
            mat = bpy.data.materials.new(key)
            fn(G(mat), *args, **kw)
            _cache[key] = mat
            return mat
        return make
    return deco


@material("plaster")
def plaster(g, color="#EEEDEA", mottle=0.0):
    """Painted plaster. mottle > 0: a hand-finished coat, its tone wandering that much either way over a few
    tens of centimetres, with a broad trowelled undulation as well as the fine grain."""
    m = g.coords("Object")
    noise = g.n("ShaderNodeTexNoise", Scale=2.5, Detail=4.0, Roughness=0.55)
    g.link(m, "Vector", noise, "Vector")
    col = g.ramp(noise, "Fac", [(0.35, _shade(color, -0.025 - mottle)), (0.65, _shade(color, 0.012 + mottle / 2))])
    g.link(col, "Color", g.bsdf, "Base Color")
    fine = g.n("ShaderNodeTexNoise", Scale=180.0, Detail=6.0, Roughness=0.7)
    g.link(m, "Vector", fine, "Vector")
    if mottle > 0:
        broad = g.n("ShaderNodeTexNoise", Scale=3.3, Detail=3.0)
        g.link(m, "Vector", broad, "Vector")
        both = g.n("ShaderNodeMath", _operation="ADD")
        g.link(fine, "Fac", both, 0)
        scaled = g.n("ShaderNodeMath", _operation="MULTIPLY")
        g.link(broad, "Fac", scaled, 0)
        scaled.inputs[1].default_value = 2.5
        g.link(scaled, "Value", both, 1)
        g.bump(both, "Value", 0.035, 0.002)
    else:
        g.bump(fine, "Fac", 0.035, 0.002)
    g.set(Roughness=0.9, **{"Specular IOR Level": 0.35})


@material("oak_floor")
def oak_floor(g, tone="#C7B59C"):
    m = g.coords("Object", (1, 1, 1))
    planks = g.n("ShaderNodeTexBrick", Scale=1.0, **{"Mortar Size": 0.0012, "Brick Width": 1.45, "Row Height": 0.19, "Bias": 0.0},
                 _offset=0.43, _squash=1.0)
    planks.inputs["Color1"].default_value = (1, 1, 1, 1)
    planks.inputs["Color2"].default_value = (0, 0, 0, 1)
    planks.inputs["Mortar"].default_value = (0, 0, 0, 1)
    g.link(m, "Vector", planks, "Vector")
    # grain: bands along each plank's length, wobbled by noise
    grain_map = g.coords("Object", (1.0, 26.0, 1.0))
    distort = g.n("ShaderNodeTexNoise", Scale=1.6, Detail=3.0)
    g.link(grain_map, "Vector", distort, "Vector")
    wave = g.n("ShaderNodeTexWave", Scale=2.4, Distortion=7.0, Detail=3.0, **{"Detail Scale": 1.2}, _wave_type="BANDS", _bands_direction="Y")
    add = g.n("ShaderNodeVectorMath", _operation="ADD")
    g.link(grain_map, "Vector", add, 0)
    g.link(distort, "Color", add, 1)
    g.link(add, "Vector", wave, "Vector")
    tone_mix = g.n("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY", Factor=0.35)
    plank_tone = g.ramp(planks, "Color", [(0.0, _shade(tone, -0.06)), (1.0, _shade(tone, 0.04))])
    grain_col = g.ramp(wave, "Fac", [(0.0, "#FFFFFF"), (0.55, "#F0E8DE"), (1.0, "#C9B49C")])
    g.link(plank_tone, "Color", tone_mix, "A")
    g.link(grain_col, "Color", tone_mix, "B")
    # each plank its own shade: the brick texture's random per-brick value
    per = g.n("ShaderNodeTexBrick", Scale=1.0, **{"Mortar Size": 0.0, "Brick Width": 1.45, "Row Height": 0.19}, _offset=0.43)
    per.inputs["Color1"].default_value = hex_rgb(_shade(tone, 0.09))
    per.inputs["Color2"].default_value = hex_rgb(_shade(tone, -0.09))
    g.link(m, "Vector", per, "Vector")
    final = g.n("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY", Factor=0.85)
    g.link(per, "Color", final, "A")
    g.link(tone_mix, "Result", final, "B")
    seam = g.n("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY")
    g.link(planks, "Fac", seam, "Factor")
    g.link(final, "Result", seam, "A")
    seam.inputs["B"].default_value = (0.55, 0.55, 0.55, 1.0)
    g.link(seam, "Result", g.bsdf, "Base Color")
    rough = g.n("ShaderNodeMapRange", **{"From Min": 0.0, "From Max": 1.0, "To Min": 0.2, "To Max": 0.34})
    g.link(wave, "Fac", rough, "Value")
    g.link(rough, "Result", g.bsdf, "Roughness")
    g.bump(planks, "Fac", 0.3, 0.002)
    g.set(**{"Coat Weight": 0.15, "Coat Roughness": 0.2})


@material("oak")
def oak(g, tone="#CDAA80", scale=22.0, axis="X", grain=0.0):
    m = g.coords("Object", (1.0, 1.0, 1.0) if axis == "X" else (1, 1, 1))
    scale = scale * 0.21  # the grain's stripes about 13 mm apart, broad like flat-sawn oak
    stretch = g.coords("Object", (1.0, scale, scale) if axis == "X" else (scale, 1.0, scale) if axis == "Y" else (scale, scale, 1.0))
    distort = g.n("ShaderNodeTexNoise", Scale=1.3, Detail=3.0)
    g.link(stretch, "Vector", distort, "Vector")
    soft = g.n("ShaderNodeVectorMath", _operation="SCALE")  # a gentle wander, not ripples
    g.link(distort, "Color", soft, 0)
    soft.inputs["Scale"].default_value = 0.35
    add = g.n("ShaderNodeVectorMath", _operation="ADD")
    g.link(stretch, "Vector", add, 0)
    g.link(soft, "Vector", add, 1)
    wave = g.n("ShaderNodeTexWave", Scale=0.8, Distortion=1.0, Detail=2.0, _wave_type="BANDS",
               _bands_direction={"X": "Y", "Y": "X", "Z": "X"}[axis])
    g.link(add, "Vector", wave, "Vector")
    col = g.ramp(wave, "Fac", [(0.0, _shade(tone, 0.01 + grain)), (0.6, tone), (1.0, _shade(tone, -0.02 - grain))])  # grain > 0: a stronger figure
    g.link(col, "Color", g.bsdf, "Base Color")
    rough = g.n("ShaderNodeMapRange", **{"To Min": 0.4, "To Max": 0.5})
    g.link(wave, "Fac", rough, "Value")
    g.link(rough, "Result", g.bsdf, "Roughness")
    g.bump(wave, "Fac", 0.004, 0.0005)
    g.set(**{"Coat Weight": 0.15, "Coat Roughness": 0.3})


@material("terrazzo")
def terrazzo(g, base="#DCD6CC"):
    """Polished terrazzo: angular marble chips packed in a pale matrix, most a few millimetres across and a
    few up to about 15 mm, close in tone to the matrix, under a polish that varies a little across the floor."""
    m = g.coords("Object")
    wob = g.n("ShaderNodeTexNoise", Scale=60.0, Detail=2.0)
    g.link(m, "Vector", wob, "Vector")
    warp = g.n("ShaderNodeVectorMath", _operation="MULTIPLY_ADD")  # chips are broken stone: wobble their outlines
    g.link(wob, "Color", warp, 0)
    warp.inputs[1].default_value = (0.0035, 0.0035, 0.0035)
    g.link(m, "Vector", warp, 2)

    def layer(scale, inset, share):
        """Cells of a Voronoi pattern shrunk to angular chips; `share` of the cells are chips, the rest matrix."""
        cell = g.n("ShaderNodeTexVoronoi", Scale=scale, Randomness=1.0, _feature="F1")
        edge = g.n("ShaderNodeTexVoronoi", Scale=scale, Randomness=1.0, _feature="DISTANCE_TO_EDGE")
        g.link(warp, "Vector", cell, "Vector")
        g.link(warp, "Vector", edge, "Vector")
        inside = g.n("ShaderNodeMath", _operation="GREATER_THAN")
        g.link(edge, "Distance", inside, 0)
        inside.inputs[1].default_value = inset
        sep = g.n("ShaderNodeSeparateColor")
        g.link(cell, "Color", sep, "Color")
        chosen = g.n("ShaderNodeMath", _operation="LESS_THAN")
        g.link(sep, "Red", chosen, 0)
        chosen.inputs[1].default_value = share
        both = g.n("ShaderNodeMath", _operation="MULTIPLY")
        g.link(inside, "Value", both, 0)
        g.link(chosen, "Value", both, 1)
        return both, sep

    fine, fine_c = layer(170.0, 0.11, 0.5)     # cells ~6 mm: chips ~3 to 5 mm
    coarse, coarse_c = layer(70.0, 0.16, 0.14)  # cells ~14 mm: a few chips ~8 to 15 mm
    mott = g.n("ShaderNodeTexNoise", Scale=3.0, Detail=5.0)
    g.link(m, "Vector", mott, "Vector")
    base_col = g.ramp(mott, "Fac", [(0.3, _shade(base, -0.03)), (0.7, _shade(base, 0.02))])
    tones = [(0.0, "#C9C1B6"), (0.3, "#ECE8E1"), (0.55, "#B3AA9E"), (0.8, "#D3C1AC"), (1.0, "#F2EFEA")]  # half the old contrast
    fine_col = g.ramp(fine_c, "Green", tones)
    coarse_col = g.ramp(coarse_c, "Blue", tones)
    mix1 = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(fine, "Value", mix1, "Factor")
    g.link(base_col, "Color", mix1, "A")
    g.link(fine_col, "Color", mix1, "B")
    mix2 = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(coarse, "Value", mix2, "Factor")
    g.link(mix1, "Result", mix2, "A")
    g.link(coarse_col, "Color", mix2, "B")
    g.link(mix2, "Result", g.bsdf, "Base Color")
    polish = g.n("ShaderNodeTexNoise", Scale=0.8, Detail=3.0)  # the polish wears a little unevenly
    g.link(m, "Vector", polish, "Vector")
    rough = g.n("ShaderNodeMapRange", **{"To Min": 0.15, "To Max": 0.3})
    g.link(polish, "Fac", rough, "Value")
    g.link(rough, "Result", g.bsdf, "Roughness")
    g.set(**{"Coat Weight": 0.15})
    g.bump(mott, "Fac", 0.01, 0.001)


@material("matte")
def matte(g, color="#1B1B1B", rough=0.45, metal=0.0, sheen=0.0, coat=0.0):
    m = g.coords("Object")
    noise = g.n("ShaderNodeTexNoise", Scale=260.0, Detail=4.0)
    g.link(m, "Vector", noise, "Vector")
    g.bump(noise, "Fac", 0.04, 0.001)
    g.set(**{"Base Color": hex_rgb(color), "Roughness": rough, "Metallic": metal, "Sheen Weight": sheen, "Coat Weight": coat})


@material("steel")
def steel(g, color="#C9CCCF", rough=0.28):
    m = g.coords("Object", (1, 60, 1))
    noise = g.n("ShaderNodeTexNoise", Scale=40.0, Detail=8.0)
    g.link(m, "Vector", noise, "Vector")
    r = g.n("ShaderNodeMapRange", **{"To Min": rough - 0.06, "To Max": rough + 0.08})
    g.link(noise, "Fac", r, "Value")
    g.link(r, "Result", g.bsdf, "Roughness")
    g.set(**{"Base Color": hex_rgb(color), "Metallic": 1.0, "Anisotropic": 0.4})


@material("fabric")
def fabric(g, color="#EDE7DD", loops=1.0, sheen=0.6, bump=0.45, weave=0.0):
    """Woven or bouclé cloth: fine loops in the bump, sheen at grazing angles. weave > 0 adds a plain weave
    (warp and weft bands, about 2 mm apart at 300)."""
    m = g.coords("Object")
    v = g.n("ShaderNodeTexVoronoi", Scale=320.0 * loops, _feature="SMOOTH_F1")
    g.link(m, "Vector", v, "Vector")
    n = g.n("ShaderNodeTexNoise", Scale=900.0, Detail=2.0)
    g.link(m, "Vector", n, "Vector")
    mix = g.n("ShaderNodeMath", _operation="ADD")
    if weave > 0:  # a fine random tooth, no regular pattern (a regular one beats against the pixels into rings)
        tooth = g.n("ShaderNodeTexNoise", Scale=weave * 2.0, Detail=1.0, Roughness=0.4)
        g.link(m, "Vector", tooth, "Vector")
        g.link(tooth, "Fac", mix, 0)
    else:
        g.link(v, "Distance", mix, 0)
    g.link(n, "Fac", mix, 1)
    tone = g.n("ShaderNodeTexNoise", Scale=6.0, Detail=3.0)
    g.link(m, "Vector", tone, "Vector")
    col = g.ramp(tone, "Fac", [(0.3, _shade(color, -0.04)), (0.7, _shade(color, 0.02))])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.bump(mix, "Value", bump, 0.003)
    g.set(Roughness=0.95, **{"Sheen Weight": sheen, "Sheen Roughness": 0.4, "Specular IOR Level": 0.25})


@material("leather")
def leather(g, color="#8E5B32", coat=0.2):
    m = g.coords("Object")
    v = g.n("ShaderNodeTexVoronoi", Scale=180.0, _feature="DISTANCE_TO_EDGE")
    g.link(m, "Vector", v, "Vector")
    tone = g.n("ShaderNodeTexNoise", Scale=4.0, Detail=4.0)
    g.link(m, "Vector", tone, "Vector")
    col = g.ramp(tone, "Fac", [(0.25, _shade(color, -0.08)), (0.75, _shade(color, 0.05))])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.bump(v, "Distance", 0.15, 0.002)
    g.set(Roughness=0.42 if coat else 0.5, **{"Coat Weight": coat, "Coat Roughness": 0.3})


@material("stone")
def stone(g, color="#E3D6C3", vein="#B9A88F", rough=0.35, scale=2.0):
    """Travertine or marble: soft bands with veins."""
    m = g.coords("Object", (scale, scale * 6, scale))
    n = g.n("ShaderNodeTexNoise", Scale=1.2, Detail=8.0, Roughness=0.6, Distortion=0.8)
    g.link(m, "Vector", n, "Vector")
    w = g.n("ShaderNodeTexWave", Scale=1.5, Distortion=9.0, Detail=6.0, _wave_type="BANDS")
    g.link(m, "Vector", w, "Vector")
    mix = g.n("ShaderNodeMath", _operation="MULTIPLY")
    g.link(n, "Fac", mix, 0)
    g.link(w, "Fac", mix, 1)
    col = g.ramp(mix, "Value", [(0.0, _shade(color, 0.03)), (0.45, color), (0.8, vein)])
    g.link(col, "Color", g.bsdf, "Base Color")
    pits = g.n("ShaderNodeTexVoronoi", Scale=140.0)
    g.link(m, "Vector", pits, "Vector")
    g.bump(pits, "Distance", 0.05, 0.001)
    g.set(Roughness=rough)


@material("concrete")
def concrete(g, color="#A9A59D", rough=0.4):
    """A sealed concrete floor, ground smooth: soft clouds of lighter and darker cement, a little aggregate
    showing where the grinding went deeper, and a sheen that varies with the wear."""
    m = g.coords("Object")
    cloud = g.n("ShaderNodeTexNoise", Scale=1.4, Detail=7.0, Roughness=0.62)
    g.link(m, "Vector", cloud, "Vector")
    fine = g.n("ShaderNodeTexNoise", Scale=38.0, Detail=5.0)
    g.link(m, "Vector", fine, "Vector")
    mix = g.n("ShaderNodeMix", _data_type="FLOAT", Factor=0.22)
    g.link(cloud, "Fac", mix, "A")
    g.link(fine, "Fac", mix, "B")
    base = g.ramp(mix, "Result", [(0.32, _shade(color, -0.06)), (0.5, color), (0.68, _shade(color, 0.05))])
    grit = g.n("ShaderNodeTexVoronoi", Scale=90.0, Randomness=1.0)
    g.link(m, "Vector", grit, "Vector")
    seen = g.n("ShaderNodeMath", _operation="LESS_THAN")
    g.link(grit, "Distance", seen, 0)
    seen.inputs[1].default_value = 0.09
    stone_col = g.ramp(grit, "Color", [(0.0, "#8E8A82"), (0.5, "#C2BDB3"), (1.0, "#77736C")])
    col = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(seen, "Value", col, "Factor")
    g.link(base, "Color", col, "A")
    g.link(stone_col, "Color", col, "B")
    g.link(col, "Result", g.bsdf, "Base Color")
    wear = g.n("ShaderNodeMapRange", **{"To Min": rough - 0.08, "To Max": rough + 0.12})
    g.link(cloud, "Fac", wear, "Value")
    g.link(wear, "Result", g.bsdf, "Roughness")
    g.bump(fine, "Fac", 0.03, 0.001)


@material("ceramic")
def ceramic(g, color="#E9E2D6", rough=0.25):
    m = g.coords("Object")
    n = g.n("ShaderNodeTexNoise", Scale=30.0, Detail=6.0)
    g.link(m, "Vector", n, "Vector")
    col = g.ramp(n, "Fac", [(0.3, _shade(color, -0.04)), (0.7, _shade(color, 0.03))])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.bump(n, "Fac", 0.05, 0.002)
    g.set(Roughness=rough, **{"Coat Weight": 0.3})


@material("leaf")
def leaf(g, color="#3E5B2C"):
    m = g.coords("UV")
    veins = g.n("ShaderNodeTexWave", Scale=9.0, Distortion=1.5, _wave_type="BANDS", _bands_direction="X")
    g.link(m, "Vector", veins, "Vector")
    w = g.coords("Object")
    tone = g.n("ShaderNodeTexNoise", Scale=7.0, Detail=2.0)  # by position: each leaf a little lighter or darker
    g.link(w, "Vector", tone, "Vector")
    col = g.ramp(tone, "Fac", [(0.25, _shade(color, -0.1)), (0.75, _shade(color, 0.1))])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.bump(veins, "Fac", 0.08, 0.001)
    g.set(Roughness=0.5, **{"Subsurface Weight": 0.35, "Subsurface Radius": (0.4, 0.8, 0.2), "Subsurface Scale": 0.01, "Coat Weight": 0.08})
    trans = g.n("ShaderNodeBsdfTranslucent")  # leaves glow where the sun is behind them
    g.link(col, "Color", trans, "Color")
    mix = g.n("ShaderNodeMixShader", Fac=0.25)
    g.link(g.bsdf, "BSDF", mix, 1)
    g.link(trans, "BSDF", mix, 2)
    g.link(mix, "Shader", g.out, "Surface")


@material("glow")
def glow(g, color="#FFE2B8", strength=8.0):
    g.set(**{"Base Color": hex_rgb(color), "Emission Color": hex_rgb(color), "Emission Strength": strength, "Roughness": 0.5})


@material("art")
def art(g, palette=("#E9E1D3", "#C46A3C", "#2E3B35", "#D9B98C"), seed=1.0, kind="blobs"):
    """An abstract painting made from shapes in the shader: soft blobs or bands of colour on canvas."""
    m = g.coords("Object")
    if kind == "bands":
        w = g.n("ShaderNodeTexWave", Scale=0.6, Distortion=1.2 + seed, Detail=1.0, _wave_type="BANDS", _bands_direction="Z")
        g.link(m, "Vector", w, "Vector")
        src, out = w, "Fac"
    else:
        v = g.n("ShaderNodeTexVoronoi", _voronoi_dimensions="4D", _feature="SMOOTH_F1", Scale=1.6, Randomness=0.9, W=seed)
        g.link(m, "Vector", v, "Vector")
        sep = g.n("ShaderNodeSeparateColor")
        g.link(v, "Color", sep, "Color")
        src, out = sep, "Red"
    col = g.ramp(src, out, [(0.0, palette[0]), (0.33, palette[1]), (0.34, palette[0]), (0.6, palette[2]), (0.61, palette[0]), (0.85, palette[3]), (1.0, palette[0])])
    g.link(col, "Color", g.bsdf, "Base Color")
    canvas = g.n("ShaderNodeTexWave", Scale=420.0, _wave_type="BANDS")
    g.link(m, "Vector", canvas, "Vector")
    g.bump(canvas, "Fac", 0.06, 0.0005)
    g.set(Roughness=0.8)


@material("window_glass")
def window_glass(g):
    """Glass you see reflections in, but that lets the sun straight through (no caustics needed)."""
    t = g.t
    t.nodes.remove(g.bsdf)
    glass = g.n("ShaderNodeBsdfPrincipled")
    glass.inputs["Base Color"].default_value = hex_rgb("#EEF1F1")
    glass.inputs["Roughness"].default_value = 0.0
    glass.inputs["Transmission Weight"].default_value = 1.0
    glass.inputs["IOR"].default_value = 1.52
    glass.inputs["Thin Wall"].default_value = True
    clear = g.n("ShaderNodeBsdfTransparent")
    lp = g.n("ShaderNodeLightPath")
    either = g.n("ShaderNodeMath", _operation="MAXIMUM")
    g.link(lp, "Is Shadow Ray", either, 0)
    g.link(lp, "Is Diffuse Ray", either, 1)
    mix = g.n("ShaderNodeMixShader")
    g.link(either, "Value", mix, "Fac")
    g.link(glass, "BSDF", mix, 1)
    g.link(clear, "BSDF", mix, 2)
    g.link(mix, "Shader", g.out, "Surface")


@material("ground")
def ground(g):
    m = g.coords("Object")
    n = g.n("ShaderNodeTexNoise", Scale=0.6, Detail=6.0)
    g.link(m, "Vector", n, "Vector")
    fine = g.n("ShaderNodeTexNoise", Scale=9.0, Detail=4.0)
    g.link(m, "Vector", fine, "Vector")
    mixn = g.n("ShaderNodeMix", _data_type="FLOAT", Factor=0.35)
    g.link(n, "Fac", mixn, "A")
    g.link(fine, "Fac", mixn, "B")
    col = g.ramp(mixn, "Result", [(0.3, "#4E5A3A"), (0.55, "#66704A"), (0.75, "#7A7655")])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.set(Roughness=0.95)
    haze(g)


def seen_straight(t):
    """1 for a ray from the camera that has not bounced off anything (it may have passed through glass), else 0."""
    lp = t.nodes.new("ShaderNodeLightPath")
    add = t.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    t.links.new(lp.outputs["Diffuse Depth"], add.inputs[0])
    t.links.new(lp.outputs["Glossy Depth"], add.inputs[1])
    lt = t.nodes.new("ShaderNodeMath")
    lt.operation = "LESS_THAN"
    t.links.new(add.outputs[0], lt.inputs[0])
    lt.inputs[1].default_value = 0.5
    return lt.outputs[0]


def exposed(t, shader_socket, out_socket, copies=4):
    """The photographer's blown-out window: shader x copies for rays seen straight, as it is for light."""
    total = shader_socket
    for _ in range(copies - 1):
        add = t.nodes.new("ShaderNodeAddShader")
        t.links.new(total, add.inputs[0])
        t.links.new(shader_socket, add.inputs[1])
        total = add.outputs[0]
    mix = t.nodes.new("ShaderNodeMixShader")
    t.links.new(seen_straight(t), mix.inputs["Fac"])
    t.links.new(shader_socket, mix.inputs[1])
    t.links.new(total, mix.inputs[2])
    t.links.new(mix.outputs[0], out_socket)


def haze(g, color="#DCE3EA", strength=2.6, reach=200.0):
    """Air between the camera and a far surface: mixes the surface towards a glow of sky colour,
    1 - exp(-distance / reach) of the way. Then lifted 2 EV for rays seen straight (see exposed)."""
    cam = g.n("ShaderNodeCameraData")
    k = g.n("ShaderNodeMath", _operation="DIVIDE")
    g.link(cam, "View Distance", k, 0)
    k.inputs[1].default_value = -reach
    e = g.n("ShaderNodeMath", _operation="EXPONENT")
    g.link(k, "Value", e, 0)
    fac = g.n("ShaderNodeMath", _operation="SUBTRACT")
    fac.inputs[0].default_value = 1.0
    g.link(e, "Value", fac, 1)
    glow = g.n("ShaderNodeEmission", Strength=strength)
    glow.inputs["Color"].default_value = hex_rgb(color)
    surface = g.out.inputs["Surface"].links[0].from_socket
    mix = g.n("ShaderNodeMixShader")
    g.link(fac, "Value", mix, "Fac")
    g.t.links.new(surface, mix.inputs[1])
    g.link(glow, "Emission", mix, 2)
    exposed(g.t, mix.outputs["Shader"], g.out.inputs["Surface"])


def _desaturate(h, amount):
    """A hex colour moved towards its own grey by amount (0 to 1)."""
    c = [int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    y = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    return "#" + "".join(f"{round(v + (y - v) * amount):02X}" for v in c)


def _shade(h, amount):
    """A hex colour made lighter (amount > 0) or darker (amount < 0), as hex."""
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    c = [max(0, min(255, round(v + (255 - v) * amount if amount > 0 else v * (1 + amount)))) for v in c]
    return "#" + "".join(f"{v:02X}" for v in c)


@material("foliage")
def foliage(g, color="#4D6339"):
    """Leaves seen from a distance: varied greens, a little sheen, light coming through them."""
    m = g.coords("Object")
    n = g.n("ShaderNodeTexNoise", Scale=0.7, Detail=3.0)
    g.link(m, "Vector", n, "Vector")
    fine = g.n("ShaderNodeTexNoise", Scale=6.0, Detail=1.0)
    g.link(m, "Vector", fine, "Vector")
    both = g.n("ShaderNodeMix", _data_type="FLOAT", Factor=0.5)
    g.link(n, "Fac", both, "A")
    g.link(fine, "Fac", both, "B")
    col = g.ramp(both, "Result", [(0.3, "#4A6232"), (0.5, "#5E7A3A"), (0.7, "#7E9A4E")])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.set(Roughness=0.5)
    trans = g.n("ShaderNodeBsdfTranslucent")
    g.link(col, "Color", trans, "Color")
    mix = g.n("ShaderNodeMixShader", Fac=0.3)
    g.link(g.bsdf, "BSDF", mix, 1)
    g.link(trans, "BSDF", mix, 2)
    g.link(mix, "Shader", g.out, "Surface")
    haze(g)


@material("facade")
def facade(g, wall="#D8CFC2", glass="#1E2328", bay=3.0, storey=3.2):
    """A neighbouring building's face: rendered or brick-coloured wall with a grid of dark glazed windows."""
    m = g.coords("Object")
    sep = g.n("ShaderNodeSeparateXYZ")
    g.link(m, "Vector", sep, "Vector")

    def op(kind, a, b=None, value=None, a_out=0, b_out=0):
        node = g.n("ShaderNodeMath", _operation=kind)
        g.link(a, a_out, node, 0)
        if b is not None:
            g.link(b, b_out, node, 1)
        elif value is not None:
            node.inputs[1].default_value = value
        return node

    u = op("ADD", sep, sep, a_out="X", b_out="Y")
    fu = op("FRACT", op("DIVIDE", u, value=bay))
    fv = op("FRACT", op("DIVIDE", sep, value=storey, a_out="Z"))
    inside = op("MULTIPLY", op("MULTIPLY", op("GREATER_THAN", fu, value=0.2), op("LESS_THAN", fu, value=0.8)),
                op("MULTIPLY", op("GREATER_THAN", fv, value=0.3), op("LESS_THAN", fv, value=0.86)))
    framed = op("MULTIPLY", op("MULTIPLY", op("GREATER_THAN", fu, value=0.17), op("LESS_THAN", fu, value=0.83)),
                op("MULTIPLY", op("GREATER_THAN", fv, value=0.26), op("LESS_THAN", fv, value=0.9)))
    tone = g.n("ShaderNodeTexNoise", Scale=0.15, Detail=3.0)
    g.link(m, "Vector", tone, "Vector")
    wall_col = g.ramp(tone, "Fac", [(0.3, _shade(wall, -0.06)), (0.7, _shade(wall, 0.04))])
    sky_in = g.n("ShaderNodeTexNoise", Scale=0.4, Detail=2.0)
    g.link(m, "Vector", sky_in, "Vector")
    glass_plain = g.ramp(sky_in, "Fac", [(0.35, glass), (0.65, "#6E7A84")])
    # one random number per window, from its bay and storey
    cell = g.n("ShaderNodeCombineXYZ")
    g.link(op("FLOOR", op("DIVIDE", u, value=bay)), 0, cell, "X")
    g.link(op("FLOOR", op("DIVIDE", sep, value=storey, a_out="Z")), 0, cell, "Y")
    rnd = g.n("ShaderNodeTexWhiteNoise", _noise_dimensions="3D")
    g.link(cell, "Vector", rnd, "Vector")
    blind = op("MULTIPLY", op("LESS_THAN", rnd, value=0.22, a_out="Value"), op("GREATER_THAN", fv, value=0.56))
    with_blind = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(blind, "Value", with_blind, "Factor")
    g.link(glass_plain, "Color", with_blind, "A")
    with_blind.inputs["B"].default_value = hex_rgb("#D6D0C4")
    # the reveal's shadow along the head and one jamb of each pane
    reveal = op("MINIMUM", op("ADD", op("LESS_THAN", fu, value=0.235), op("GREATER_THAN", fv, value=0.83)), value=1.0)
    shade_rev = g.n("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY")
    g.link(reveal, "Value", shade_rev, "Factor")
    g.link(with_blind, "Result", shade_rev, "A")
    shade_rev.inputs["B"].default_value = (0.5, 0.5, 0.52, 1.0)
    # a mullion down the middle and a transom
    bars = op("MINIMUM", op("ADD", op("MULTIPLY", op("GREATER_THAN", fu, value=0.488), op("LESS_THAN", fu, value=0.512)),
                                   op("MULTIPLY", op("GREATER_THAN", fv, value=0.66), op("LESS_THAN", fv, value=0.675))), value=1.0)
    glass_col = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(bars, "Value", glass_col, "Factor")
    g.link(shade_rev, "Result", glass_col, "A")
    glass_col.inputs["B"].default_value = hex_rgb("#D9D8D4")
    frame = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(framed, "Value", frame, "Factor")
    g.link(wall_col, "Color", frame, "A")
    frame.inputs["B"].default_value = hex_rgb("#E4E3DF")
    mix = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(inside, "Value", mix, "Factor")
    g.link(frame, "Result", mix, "A")
    g.link(glass_col, "Result", mix, "B")
    g.link(mix, "Result", g.bsdf, "Base Color")
    rough = g.n("ShaderNodeMapRange", **{"To Min": 0.85, "To Max": 0.04})
    g.link(inside, "Value", rough, "Value")
    g.link(rough, "Result", g.bsdf, "Roughness")
    haze(g)


@material("screen on")
def screen_on(g):
    """A monitor left on: a dim editor, short lines of light text on a dark ground, under glossy glass."""
    m = g.coords("Object")
    lines = g.n("ShaderNodeTexBrick", Scale=1.0, **{"Mortar Size": 0.004, "Brick Width": 0.07, "Row Height": 0.014, "Bias": 0.0},
                _offset=0.37, _squash=1.0)
    lines.inputs["Color1"].default_value = (1, 1, 1, 1)
    lines.inputs["Color2"].default_value = (0, 0, 0, 1)
    lines.inputs["Mortar"].default_value = (0, 0, 0, 1)
    sep = g.n("ShaderNodeSeparateXYZ")  # the screen stands in the XZ plane: lay its rows along X, stacked up Z
    g.link(m, "Vector", sep, "Vector")
    xz = g.n("ShaderNodeCombineXYZ")
    g.link(sep, "X", xz, "X")
    g.link(sep, "Z", xz, "Y")
    g.link(xz, "Vector", lines, "Vector")
    bw = g.n("ShaderNodeRGBToBW")  # each token its own random shade: keep the lighter half as text
    g.link(lines, "Color", bw, "Color")
    keep = g.n("ShaderNodeMath", _operation="GREATER_THAN")
    g.link(bw, "Val", keep, 0)
    keep.inputs[1].default_value = 0.45
    col = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(keep, "Value", col, "Factor")
    col.inputs["A"].default_value = hex_rgb("#1E1E1E")
    col.inputs["B"].default_value = hex_rgb("#8A97A3")
    g.link(col, "Result", g.bsdf, "Emission Color")
    g.set(**{"Base Color": hex_rgb("#0B0C0D"), "Roughness": 0.05, "Coat Weight": 0.8, "Emission Strength": 0.3})


@material("screen site")
def screen_site(g, seed=0):
    """A website on a screen, lit: a pale page under a dark navigation bar, a headline, a button and rows of
    text, and a large picture: a landscape (sky, a hill line, ground) in two of the company's colours. seed
    picks the colours and the layout (picture right, picture left, or a wide picture over centred text), so
    each screen shows a different site."""
    tones = [("#C9A57B", "#5B6B5A"), ("#B9653E", "#2E3B35"), ("#7E8B74", "#D9CBB5"), ("#2E3B35", "#C9A57B")][seed % 4]
    layout = seed % 3
    m = g.n("ShaderNodeAttribute", _attribute_name="screen_uv")  # 0 to 1 across the page (pieces.site_screen)
    sep = g.n("ShaderNodeSeparateXYZ")
    g.link(m, "Vector", sep, "Vector")
    xs = sep
    if layout == 1:  # mirrored: the picture on the left
        flip = g.n("ShaderNodeMath", _operation="SUBTRACT")
        flip.inputs[0].default_value = 1.0
        g.link(sep, "X", flip, 1)
        comb = g.n("ShaderNodeCombineXYZ")
        g.link(flip, "Value", comb, "X")
        g.link(sep, "Y", comb, "Y")
        g.link(sep, "Z", comb, "Z")
        xs = g.n("ShaderNodeSeparateXYZ")
        g.link(comb, "Vector", xs, "Vector")

    def rng(src, axis, lo, hi):
        a = g.n("ShaderNodeMath", _operation="GREATER_THAN")
        b = g.n("ShaderNodeMath", _operation="LESS_THAN")
        a.inputs[1].default_value, b.inputs[1].default_value = lo, hi
        g.link(src, axis, a, 0)
        g.link(src, axis, b, 0)
        both = g.n("ShaderNodeMath", _operation="MULTIPLY")
        g.link(a, "Value", both, 0)
        g.link(b, "Value", both, 1)
        return both

    def rect(x0, x1, z0, z1, src=None):
        r = g.n("ShaderNodeMath", _operation="MULTIPLY")
        g.link(rng(src or xs, "X", x0, x1), "Value", r, 0)
        g.link(rng(sep, "Z", z0, z1), "Value", r, 1)
        return r

    # the picture: a sky fading to pale at the horizon, a soft hill line, darker ground below
    px0, px1, pz0, pz1 = (0.52, 0.96, 0.12, 0.84) if layout < 2 else (0.04, 0.96, 0.44, 0.86)
    along = g.n("ShaderNodeCombineXYZ")
    sx = g.n("ShaderNodeMath", _operation="MULTIPLY")
    g.link(sep, "X", sx, 0)
    sx.inputs[1].default_value = 3.0
    g.link(sx, "Value", along, "X")
    along.inputs["Y"].default_value = 1.7 * seed
    hill = g.n("ShaderNodeTexNoise", Scale=1.0, Detail=3.0, Roughness=0.5)
    g.link(along, "Vector", hill, "Vector")
    hz = g.n("ShaderNodeMapRange", **{"To Min": pz0 + 0.3 * (pz1 - pz0), "To Max": pz0 + 0.62 * (pz1 - pz0)})
    g.link(hill, "Fac", hz, "Value")
    is_sky = g.n("ShaderNodeMath", _operation="GREATER_THAN")
    g.link(sep, "Z", is_sky, 0)
    g.link(hz, "Result", is_sky, 1)
    up = g.n("ShaderNodeMapRange", **{"From Min": pz0, "From Max": pz1})
    g.link(sep, "Z", up, "Value")
    sky = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(up, "Result", sky, "Factor")
    sky.inputs["A"].default_value = hex_rgb(_shade(tones[0], 0.55))
    sky.inputs["B"].default_value = hex_rgb(_shade(tones[0], 0.1))
    ground = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(up, "Result", ground, "Factor")
    ground.inputs["A"].default_value = hex_rgb(_shade(tones[1], -0.25))
    ground.inputs["B"].default_value = hex_rgb(tones[1])
    pic = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(is_sky, "Value", pic, "Factor")
    g.link(ground, "Result", pic, "A")
    g.link(sky, "Result", pic, "B")

    text = g.n("ShaderNodeTexBrick", Scale=1.0, **{"Mortar Size": 0.018, "Brick Width": 0.11, "Row Height": 0.05, "Bias": 0.0}, _offset=0.5)
    text.inputs["Color1"].default_value = hex_rgb("#A39E95")
    text.inputs["Color2"].default_value = hex_rgb("#B2ADA4")
    text.inputs["Mortar"].default_value = hex_rgb("#F4F1EA")
    flat = g.n("ShaderNodeCombineXYZ")  # the page laid flat for the text rows: across, then up
    g.link(sep, "X", flat, "X")
    g.link(sep, "Z", flat, "Y")
    g.link(flat, "Vector", text, "Vector")
    if layout < 2:
        layers = [((0.06, 0.44, 0.1, 0.38), (text, "Color")),       # body text
                  ((0.06, 0.4, 0.62, 0.7), "#2A2724"),              # the headline, two lines
                  ((0.06, 0.3, 0.53, 0.6), "#2A2724"),
                  ((0.06, 0.2, 0.43, 0.49), tones[0]),              # a button
                  ((px0, px1, pz0, pz1), (pic, "Result"))]          # the picture
    else:
        layers = [((px0, px1, pz0, pz1), (pic, "Result")),
                  ((0.25, 0.75, 0.3, 0.37), "#2A2724"),             # the headline under it, centred
                  ((0.2, 0.8, 0.08, 0.24), (text, "Color")),
                  ((0.42, 0.58, 0.26, 0.29), tones[0])]
    layers += [((0.0, 1.0, 0.9, 1.01), "#22201E"),                   # the navigation bar
               ((0.05, 0.16, 0.93, 0.97), "#E9E4DA"),                # the site's name in it
               ((0.7, 0.94, 0.935, 0.965), "#8C8780")]               # its menu
    prev = None
    for (x0, x1, z0, z1), fill in layers:
        mix = g.n("ShaderNodeMix", _data_type="RGBA")
        g.link(rect(x0, x1, z0, z1, sep if (x0, x1) in ((0.0, 1.0), (0.05, 0.16), (0.7, 0.94)) else None), "Value", mix, "Factor")
        if prev is None:
            mix.inputs["A"].default_value = hex_rgb("#F4F1EA")  # the page
        else:
            g.link(prev, "Result", mix, "A")
        if isinstance(fill, str):
            mix.inputs["B"].default_value = hex_rgb(fill)
        else:
            g.link(fill[0], fill[1], mix, "B")
        prev = mix
    g.set(**{"Base Color": (0.0, 0.0, 0.0, 1.0), "Emission Strength": 0.5, "Roughness": 0.08, "Coat Weight": 0.6})
    g.link(prev, "Result", g.bsdf, "Emission Color")


@material("screen wallpaper")
def screen_wallpaper(g):
    """A monitor left on at its desktop: a soft dusk gradient, no text, under glossy glass."""
    m = g.coords("Generated")  # 0 to 1 across the screen's box
    sep = g.n("ShaderNodeSeparateXYZ")
    g.link(m, "Vector", sep, "Vector")
    across = g.n("ShaderNodeMath", _operation="MULTIPLY")
    g.link(sep, "X", across, 0)
    across.inputs[1].default_value = 0.25
    sweep = g.n("ShaderNodeMath", _operation="MULTIPLY_ADD")  # mostly up the screen, a little across it
    g.link(sep, "Z", sweep, 0)
    sweep.inputs[1].default_value = 0.8
    g.link(across, "Value", sweep, 2)
    ramp = g.ramp(sweep, "Value", [(0.0, "#1F3347"), (0.55, "#5E7488"), (1.0, "#D6A47C")])
    g.link(ramp, "Color", g.bsdf, "Emission Color")
    g.set(**{"Base Color": hex_rgb("#0B0C0D"), "Roughness": 0.05, "Coat Weight": 0.8, "Emission Strength": 0.6})


@material("skin")
def skin(g, color="#c8926e", lips=False):
    """Skin: light goes in and scatters (reddest deepest), faint blotches of tone, pores in the bump."""
    m = g.coords("Object")
    tone = g.n("ShaderNodeTexNoise", Scale=45.0, Detail=3.0)
    g.link(m, "Vector", tone, "Vector")
    color = _desaturate(color, 0.36)
    col = g.ramp(tone, "Fac", [(0.35, _shade(color, -0.2)), (0.65, _shade(color, -0.12))])  # albedo below the screen colour: skin is darker than it looks
    flush_at = g.n("ShaderNodeAttribute", _attribute_name="flush")  # nose, cheeks, ears (people.py)
    blush = g.n("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY")
    g.link(flush_at, "Fac", blush, "Factor")
    g.link(col, "Color", blush, "A")
    blush.inputs["B"].default_value = (0.92, 0.63, 0.6, 1.0)
    lash_at = g.n("ShaderNodeAttribute", _attribute_name="lash")  # lashes, lid shadow, the mouth's line (people.py)
    lash = g.n("ShaderNodeMix", _data_type="RGBA")
    g.link(lash_at, "Fac", lash, "Factor")
    g.link(blush, "Result", lash, "A")
    lash.inputs["B"].default_value = hex_rgb(_shade(color, -0.82))
    g.link(lash, "Result", g.bsdf, "Base Color")
    pores = g.n("ShaderNodeTexNoise", Scale=3300.0, Detail=2.0)
    g.link(m, "Vector", pores, "Vector")
    g.bump(pores, "Fac", 0.05, 0.0003)
    oil = g.n("ShaderNodeTexNoise", Scale=250.0, Detail=2.0)  # oilier and duller in patches a few mm across
    g.link(m, "Vector", oil, "Vector")
    rough = g.n("ShaderNodeMapRange", **{"To Min": 0.3, "To Max": 0.46})  # 0.38 on average, oilier in patches
    g.link(oil, "Fac", rough, "Value")
    g.link(rough, "Result", g.bsdf, "Roughness")
    g.set(**{"Subsurface Weight": 0.65, "Subsurface Radius": (1.0, 0.4, 0.2), "Subsurface Scale": 0.006, "IOR": 1.4,
             "Specular IOR Level": 0.5, "Coat Weight": 0.04 if lips else 0.03, "Coat Roughness": 0.3})


@material("knit")
def knit(g, color="#2f4a5c", rib=False):
    """A fine-gauge knit: stitches in vertical ribs about 3 mm apart (1.5 mm and deeper in a ribbed band), a soft fuzz."""
    m = g.coords("Object")
    ribs = g.n("ShaderNodeTexWave", Scale=210.0 if rib else 105.0, Distortion=0.6, Detail=1.0, _wave_type="BANDS", _bands_direction="X")
    g.link(m, "Vector", ribs, "Vector")
    stitch = g.n("ShaderNodeTexVoronoi", Scale=700.0, _feature="SMOOTH_F1")
    g.link(m, "Vector", stitch, "Vector")
    add = g.n("ShaderNodeMath", _operation="ADD")
    g.link(ribs, "Fac", add, 0)
    g.link(stitch, "Distance", add, 1)
    tone = g.n("ShaderNodeTexNoise", Scale=8.0, Detail=3.0)
    g.link(m, "Vector", tone, "Vector")
    col = g.ramp(tone, "Fac", [(0.3, _shade(color, -0.05)), (0.7, _shade(color, 0.03))])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.bump(add, "Value", 0.55 if rib else 0.22, 0.002)
    g.set(Roughness=0.92, **{"Sheen Weight": 0.6, "Sheen Roughness": 0.35, "Specular IOR Level": 0.2})


@material("eye")
def eye(g, color="#C9BDB0"):
    """An eye: matte under a wet, glassy coat that carries the window's glint."""
    g.set(**{"Base Color": hex_rgb(color), "Roughness": 0.35, "Coat Weight": 1.0, "Coat Roughness": 0.03, "Coat IOR": 1.38,
             "Subsurface Weight": 0.2, "Subsurface Radius": (0.6, 0.4, 0.3), "Subsurface Scale": 0.003})


@material("cornea")
def cornea(g):
    """The clear front of the eye: wet and glassy, so the window shows in it."""
    g.set(**{"Base Color": (1.0, 1.0, 1.0, 1.0), "Roughness": 0.02, "Transmission Weight": 1.0, "IOR": 1.376})


@material("hair")
def hair(g, color="#3a261f"):
    """Hair strands: the physically based hair shader, coloured directly, each strand a little different."""
    g.t.nodes.remove(g.bsdf)
    h = g.n("ShaderNodeBsdfHairPrincipled", _parametrization="COLOR")
    info = g.n("ShaderNodeHairInfo")  # darker at the root, lighter at the tip
    grad = g.n("ShaderNodeMix", _data_type="RGBA")
    grad.inputs["A"].default_value = hex_rgb(_shade(color, -0.12))
    grad.inputs["B"].default_value = hex_rgb(_shade(color, 0.03))
    g.link(info, "Intercept", grad, "Factor")
    g.link(grad, "Result", h, "Color")
    sockets = {s.name: s for s in h.inputs}  # Blender won't look "Random Color" up by name, so walk the list
    for k, v in (("Roughness", 0.36), ("Radial Roughness", 0.38), ("Coat", 0.0), ("IOR", 1.55),
                 ("Random Color", 0.12), ("Random Roughness", 0.15)):
        sockets[k].default_value = v
    g.link(h, "BSDF", g.out, "Surface")


@material("hair cap")
def hair_cap(g, color="#3a261f"):
    """Under the strands, the scalp shaded the hair's colour, so it reads as thick from every side."""
    m = g.coords("Object")
    streak = g.n("ShaderNodeTexWave", Scale=160.0, Distortion=4.0, Detail=2.0, _wave_type="BANDS", _bands_direction="Z")
    g.link(m, "Vector", streak, "Vector")
    col = g.ramp(streak, "Fac", [(0.2, _shade(color, -0.06)), (0.8, _shade(color, 0.03))])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.set(Roughness=0.55, **{"Sheen Weight": 0.4, "Sheen Roughness": 0.3})


@material("asphalt")
def asphalt(g):
    m = g.coords("Object")
    n = g.n("ShaderNodeTexNoise", Scale=40.0, Detail=6.0)
    g.link(m, "Vector", n, "Vector")
    col = g.ramp(n, "Fac", [(0.3, "#3A3B3D"), (0.7, "#55565A")])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.set(Roughness=0.9)
    haze(g)


@material("glass")
def glass(g, tint="#F2F5F4"):
    """Clear glass for carafes and tumblers."""
    g.set(**{"Base Color": hex_rgb(tint), "Roughness": 0.0, "Transmission Weight": 1.0, "IOR": 1.5, "Thin Wall": True})


@material("outdoor")
def outdoor(g, color="#CBC5BA", rough=0.85):
    """A plain outside surface (parapets, frames, far roofs), fading into the haze."""
    g.set(**{"Base Color": hex_rgb(color), "Roughness": rough})
    haze(g)
