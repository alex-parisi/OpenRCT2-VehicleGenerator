# Blender Add-on Reference

A complete reference for every control the OpenRCT2-VehicleGenerator Blender
add-on exposes: what each setting does, its valid values and default, how it maps
into the exported `object.json` / sprites, and the gotchas worth knowing.

For a guided walkthrough that builds a working vehicle start-to-finish, read the
[tutorial](blender-plugin-tutorial.md) instead — this document is the lever-by-lever
manual you reach for once you know the workflow.

## Where the UI lives

Everything is authored from the **OpenRCT2** tab of the 3D Viewport sidebar
(press **N** in the viewport, then click the *OpenRCT2* tab). There are two
panels:

| Panel | Scope | Source |
|---|---|---|
| **OpenRCT2 Vehicle** | Ride-wide settings (one set per scene) | `VG_PT_ride` |
| **Selected Object** → *Vehicle* | The active object's role + its materials | `VG_PT_object_view3d` |

The ride-wide panel writes to `scene.vg_ride`; the per-object panel writes to
`object.vg_object` and `material.vg_material`. Nothing is stored in YAML — the
whole vehicle lives in the `.blend` file as native Blender properties.

The two action buttons at the bottom of the **OpenRCT2 Vehicle** panel drive the
pipeline:

- **Test Render** (`vg.test_render`) — renders a *single* viewpoint quickly and
  loads it into an open Image Editor. Use it to iterate on geometry, materials,
  and lighting without paying for all 4 600+ sprites. It reports an error in the
  Blender header if the scene is invalid (e.g. no Body object, a bad rider
  pairing) — the same validation the full export runs.
- **Export .parkobj** (`vg.export_parkobj`) — renders *every* sprite group you
  selected and writes a complete `.parkobj`. It opens a file selector
  (pre-filled from the Object ID), then renders on a background thread with a
  spinner in the status bar. On failure the full traceback is printed to the
  system console and the header shows a short error.

> The exported `.parkobj` goes in your OpenRCT2 `object/` folder. **Restart
> OpenRCT2** after installing — it does not hot-reload the object directory.

---

## Panel: OpenRCT2 Vehicle (ride-wide)

### Identity

| Field | Property | Default | Notes |
|---|---|---|---|
| **Object ID** | `id` | `openrct2vg.ride.my_vehicle` | The object's unique id. **Use your own namespace** (`openrct2vg.ride.*` or `<author>.ride.*`). Matching a vanilla id (e.g. `rct2.ride.wooden_rc_trains`) does **not** cleanly override it — the engine keeps both and you can't tell them apart in the dropdown. |
| **Original ID** | `original_id` | *(blank)* | The vanilla object this one derives from / overrides. Optional; leave blank for a standalone object. |
| **Name** | `name` | `My Vehicle` | Display name in the build menu. |
| **Description** | `description` | *(blank)* | Free-text description. |
| **Capacity** | `capacity` | `2 people per car` | Human-readable capacity string shown in-game. This is descriptive text only — the *actual* seat count is derived from how many Rider objects you place (see [Riders](#role-rider-seat)). |
| **Authors** | `authors` | *(blank)* | Comma-separated list. Split on commas at export; whitespace trimmed. |
| **Version** | `version` | `1.0` | Object version string. |
| **Ride Type** | `ride_type` | *(first in list)* | Which OpenRCT2 ride/track type this vehicle is for. The list is read from the add-on's bundled `track_types.json`. This determines the built-in track sprites the engine pairs with your vehicle (your `.parkobj` ships only the vehicle sprites). **Pick the track type you're actually targeting** — it governs the sprite groups that make sense and the cars-per-train limits. |
| **Scale** | `scale_preset` | `Realistic` | How many OBJ units map to one OpenRCT2 tile. See below. |
| **Units / Tile** | `units_per_tile` | `TILE_SIZE` | Only shown when **Scale** is *Custom*. The raw units-per-tile value. |

**Scale** options:

- **Realistic (`TILE_SIZE` m/tile)** — model in real-world metres; one tile is
  `TILE_SIZE` metres across. Matches RCT2's real-world scale.
- **1 unit = 1 tile** — model in tiles; one OBJ unit spans a whole tile.
- **Custom** — reveals the **Units / Tile** field so you can type an arbitrary
  value.

Scale drives sprite size and the model→game conversions for car spacing and
rider positions, so it must match the scale you modelled at. Picking a preset
writes its value into **Units / Tile**; choosing *Custom* lets you edit that
number directly.

### Sprites

| Field | Property | Default | Notes |
|---|---|---|---|
| **All Sprite Groups** | `sprites_all` | **on** | Render every sprite group. Safe default; produces the largest output (a full coaster is ~4 640 vehicle sprites + 3 preview entries). |

When **All Sprite Groups** is **off**, a 2-column grid of per-group checkboxes
appears — one per entry in `SPRITE_GROUP_NAMES`. Tick only the groups your track
type uses to shrink the output. The 16 groups:

`flat`, `gentle_slopes`, `steep_slopes`, `vertical_slopes`, `diagonals`,
`banked_turns`, `inline_twists`, `slope_bank_transition`,
`diagonal_bank_transition`, `sloped_bank_transition`, `banked_sloped_turns`,
`banked_slope_transition`, `corkscrews`, `zero_g_rolls`,
`diagonal_sloped_bank_transition`, `dive_loops`.

If you turn off *All Sprite Groups* and tick **nothing**, the exporter falls
back to rendering just `flat` (the default-on group) so you always get a valid
object. Some groups imply others at load time (e.g. `dive_loops` pulls in
`zero_g_rolls`, banking pulls in `diagonal_bank_transition`), so the rendered set
may be a superset of exactly what you ticked — that's expected.

> Rendering fewer groups is purely an output-size / render-time optimization. If
> you're unsure which groups a track type needs, leave *All Sprite Groups* on.

### Train

| Field | Property | Default | Notes |
|---|---|---|---|
| **Min Cars / Train** | `min_cars` | `1` | Fewest cars a train of this vehicle can have (≥ 1). |
| **Max Cars / Train** | `max_cars` | `8` | Most cars a train can have (≥ 1). |
| **Zero Cars** | `zero_cars` | `0` | Cars at the **front** of the train that carry no riders — engines, decorative locomotives, leading dummy cars. They're still rendered, but the engine won't seat peeps in them. Leave at `0` for a train where every car holds riders. |
| **Build Menu Priority** | `build_menu_priority` | `0` | Ordering weight in the vehicle build menu (≥ 0). Hard to derive from scratch; copy the value from a vanilla vehicle of the same track type. |
| **Running Sound** | `running_sound` | *(first in list)* | The friction/rolling sound. Options: `wooden_old`, `wooden`, `steel`, `steel_smooth`, `train`, `engine`. |
| **Secondary Sound** | `secondary_sound` | *(first in list)* | The secondary effect sound. Options: `scream1`, `scream2`, `scream3`, `bell`. |

**Ride Flags** (one checkbox each, all default **off**):

| Flag | Property | Meaning |
|---|---|---|
| **No Collision Crashes** | `rf_no_collision_crashes` | Trains pass through each other instead of crashing on collision. |
| **Rider Controls Speed** | `rf_rider_controls_speed` | Riders control the car's speed (e.g. powered/pedal rides). |

> **Build Menu Priority**, **Draw Order**, and **Effect Visual** are the
> settings hardest to get right by hand and the most likely to produce glitchy
> cars when wrong. The strong recommendation is to copy them from a vanilla
> vehicle of the same track type (browse the
> [OpenRCT2/objects](https://github.com/OpenRCT2/objects) repo).

### Default Colours

A list of up to **3** colour presets shown in the build menu (OpenRCT2's hard
cap). Each preset is three colours:

| Column | Property | Default |
|---|---|---|
| **Main** | `main` | `bright_red` |
| **Secondary** | `secondary` | `black` |
| **Tertiary** | `tertiary` | `grey` |

Each colour is chosen from the 32 RCT2 palette colour names (`black`, `grey`,
`white`, `dark_purple`, … `light_pink`). Use the **+** / **−** buttons to add and
remove presets; adding a 4th is refused with a warning. **Main** recolours
materials in the *Remap 1* region, **Secondary** recolours *Remap 2*, and
**Tertiary** recolours *Remap 3* (see [material regions](#materials)).

If you define no presets, the export uses a single default of
`[bright_red, black, grey]`.

### Car Types

> Walkthrough: [Tutorial → Multiple Car Types](blender-plugin-tutorial.md#multiple-car-types).

A train can mix several *car-type variants* — a distinct **Front** (head/engine)
car, a **Rear** (tail) car, and the **Default** car used in between. Each variant
becomes one `vehicles[]` entry, and OpenRCT2 picks which to draw at each train
position.

**With no car types defined, the whole scene is exported as a single default
car** using built-in defaults — this is the common case and all most vehicles
need. The panel shows an info line to that effect. Add car types only when you
need per-position variants.

Use **+** / **−** to add/remove entries. Each car type has its own settings,
shown below the list when selected:

| Field | Property | Default | Notes |
|---|---|---|---|
| **Name** | `name` | `Car Type N` | Label only (also editable inline in the list). |
| **Collection** | `collection` | *(none)* | The Blender **Collection** holding this variant's objects (body, riders, restraints). A car type's geometry comes from this collection, **not** the whole scene. Required for every assigned car type. |
| **Collection Offset** | `offset` | `(0, 0, 0)` | A rigid translation (Blender X/Y/Z) that is **subtracted back out** at export. See below. |
| **Slot** | `slot` | `(none)` | Which train position this variant fills. See below. |
| **Preview Tab Car** | `preview_tab` | **off** | Show this variant in the build-menu preview tab. Only one car type can be the preview car; ticking it clears the flag on all others. |
| **Mass** | `mass` | `100` | Physics mass of the car (≥ 0). A heavy engine vs. light trailing cars. |
| **Spacing** | `spacing` | `2.0` | Distance between this car and the next along the track (≥ 0). |
| **Draw Order** | `draw_order` | `1` | Sprite draw-order/layering hint (≥ 0). Copy from a vanilla vehicle if unsure. |
| **Effect Visual** | `effect_visual` | `1` | Effect-visual id (≥ 0). Copy from a vanilla vehicle if unsure. |

**Slot** options (slots are **unique** — assigning one already held by another
car type clears it from that other car type):

- **(none)** — don't include this car type in the output.
- **Default** — the standard car for the middle of the train. **You need at
  least one car type in the Default slot.** (The first car type you add is set to
  Default automatically.)
- **Front (head car)** — used for the lead car. Optional.
- **Rear (tail car)** — used for the last car. Optional.

> *Second* and *Third* slots exist in the underlying enum but are intentionally
> hidden — the loader parses them but the exporter doesn't emit them yet.

**Vehicle Flags** (one checkbox each, all default **off**):

| Flag | Property | Meaning |
|---|---|---|
| **Secondary Remap** | `vf_secondary_remap` | This car uses the secondary remap colour. |
| **Tertiary Remap** | `vf_tertiary_remap` | This car uses the tertiary remap colour. |
| **Riders Scream** | `vf_riders_scream` | Riders make scream sounds on this car. |

> The fourth vehicle flag, *Restraint Animation*, is **not** shown — the add-on
> sets it automatically whenever the car contains a Restraint object.

#### Collection Offset, in detail

If you stage several collections in one scene, their geometry piles up at the
origin. To author them comfortably, **move a collection aside** in the viewport
(select its objects, grab, translate), then record that *same* translation in the
car type's **Collection Offset**. At export the offset is subtracted from every
model position, so the car still renders centred — the field exists purely to let
you spread variants out in the viewport.

It is a **rigid-translation undo only**. It is authored in Blender world space
and rotated into OBJ space internally. Rotating or scaling a collection as a whole
is **not** compensated — only a bulk move is. Leave it at `(0, 0, 0)` (the
default, a no-op) for collections already modelled at the origin.

### Custom Lighting

A collapsible section (toggle the **Custom Lighting** header to expand). By
default the renderer uses a hand-tuned 9-light default rig. Add one or more
lights here to **replace** the entire default rig with your own. With no lights
defined, the defaults are used and an info line says so.

Each light:

| Field | Property | Default | Notes |
|---|---|---|---|
| **Type** | `type` | `diffuse` | `Diffuse` (directional diffuse light) or `Specular` (specular highlight light). |
| **Casts Shadow** | `shadow` | **off** | Whether this light contributes to ambient-occlusion shadowing. |
| **Direction** | `direction` | `(0, 1, 0)` | Direction in OBJ space (+X forward, +Y up, +Z right). Normalized at render, so magnitude doesn't matter. |
| **Strength** | `strength` | `0.5` | Light intensity (≥ 0). |

Use **+** / **−** to add/remove lights. Custom lighting is all-or-nothing: as
soon as you add a single light, the defaults are gone and only your lights are
used — so a custom rig usually needs several lights to avoid a flat, dark render.
For reference, the default rig is a mix of eight diffuse lights and one specular
light at varying directions and strengths.

### Preview Image

| Field | Property | Default | Notes |
|---|---|---|---|
| **Preview Image** | `preview` | *(blank)* | Path to a preview image on disk. An already-paletted RCT2 PNG is used verbatim; any other image (RGB/JPEG/oversized) is resized and quantized to the RCT2 palette automatically. Optional. |

---

## Panel: Selected Object → Vehicle

Shown when a **mesh** object is active. Sets that object's part in the vehicle
and (folded in below) the OpenRCT2 settings for each of its materials.

### Role

| Field | Property | Default | Notes |
|---|---|---|---|
| **Role** | `role` | `Ignore` | This object's part in the vehicle. |

Options:

- **Ignore** — not part of the vehicle. The object is skipped entirely (no
  material controls are shown).
- **Body** — a static part of the car (chassis, seats, panels). Placed at its
  world position with no animation.
- **Restraint** — a lap bar / restraint that animates. Exposes the animation
  fields below.
- **Rider seat** — a peep mesh. Exposes the **Rider Number** field below.

> Tip: assign one object's role, then right-click the **Role** field →
> *Copy to Selected* to apply it to every selected object at once — handy for a
> multi-mesh body import.

### Role: Rider seat

> Walkthrough: [Tutorial → Riders](blender-plugin-tutorial.md#riders).

| Field | Property | Default | Notes |
|---|---|---|---|
| **Rider Number** | `rider_number` | `0` | Ordering key for pairing peeps into seat rows (≥ 0). |

Peeps are **sorted by Rider Number** and then chunked into consecutive pairs:
numbers `0`+`1` form the first seat row, `2`+`3` the second, and so on. A trailing
unpaired peep becomes a 1-peep row (single-seat cars). The object name is a stable
tiebreaker when two peeps share a number.

> **Riders are rows, not individuals at the engine level.** For a 2-across ×
> 2-rows (4-seat) car, place 4 peep meshes numbered 0/1/2/3 — that produces 2 rows
> of 2. The total seat count (`numSeats`) is *derived* from the number of peep
> meshes; there is no separate capacity field on the geometry.

**Remap auto-assignment:** you do **not** pick Remap1-vs-Remap2 per seat. The
exporter assigns them from each peep's position in its row — the **left** peep
(lower Rider Number in the pair) gets **Remap 1**, the **right** peep gets
**Remap 2**. This only rewrites materials you already marked remappable (skin,
hair, shoes are untouched), so marking one generic remappable shirt material on
every peep is enough. A material explicitly set to **Remap 3** is preserved and
never overwritten by this auto-assignment — use it for an accent that should
follow the ride's tertiary colour.

### Role: Restraint

> Walkthrough: [Tutorial → Restraint](blender-plugin-tutorial.md#restraint).

| Field | Property | Default | Notes |
|---|---|---|---|
| **Restraint Swing** | `restraint_swing_deg` | `90.0` | Total degrees the restraint swings across its 4 animation frames (the *simple* path). |
| **Anim Start Frame** | `anim_start_frame` | `1` | First scene frame to sample for *keyframed* animation (≥ 0). |
| **Anim End Frame** | `anim_end_frame` | `4` | Last scene frame to sample for keyframed animation (≥ 0). |

OpenRCT2 restraints animate over **4 frames**. There are two ways to drive them:

1. **Restraint Swing (simple path)** — the add-on linearly interpolates the bar
   from 0° to your value across the 4 frames, swinging around the object's
   **origin**. Good enough for a classic lap bar. Used whenever the restraint
   object has **no** keyframes.
2. **Keyframes (expressive path)** — if the restraint object has *any* keyframes
   (rotation, translation, or both), the add-on samples its world transform at 4
   evenly-spaced scene frames between **Anim Start Frame** and **Anim End Frame**
   and **ignores the Swing value**. This lets you use Blender's graph editor for
   easing, multi-axis swings, shoulder bars that drop *then* slide forward, etc.,
   and to scrub the timeline to preview the motion before rendering.

> **Set the object's ORIGIN to the hinge.** The restraint pivots about its
> origin, so model the pivot at the bar's hinge edge — not its centre — or it
> tears through the body when it swings. The rest pose is taken at **Anim Start
> Frame**: whatever orientation the restraint has there becomes frame 0, lined up
> with orientation `[0, 0, 0]`.

The *Restraint Animation* vehicle flag is set automatically when a Restraint
object is present — you don't set it yourself.

### Materials

Shown for any object whose role is **not** Ignore, folded in so you never have to
leave the sidebar for the Material Properties tab. If the object has more than one
material, pick the slot to edit from the list. The controls below write to the
active material's `vg_material`.

#### Region & flags

| Field | Property | Default | Notes |
|---|---|---|---|
| **Region** | `region` | `None` | How OpenRCT2 treats this material's pixels. See below. |
| **Mask** | `is_mask` | **off** | Treat this material as a mask. |
| **No Ambient Occlusion** | `no_ao` | **off** | Skip AO shading on this material. |
| **Edge AA** | `edge` | **off** | Apply background edge anti-aliasing on this material's silhouette. |
| **Dark Edge AA** | `dark_edge` | **off** | Background edge AA using the dark variant. |
| **No Bleed** | `no_bleed` | **off** | Disable colour bleed for this material. |
| **Texture** | `texture` | *(none)* | Optional image texture. **Must be saved to disk** — its file is read at export. Wins over a Base-Color-linked image node if both are present. |

**Region** options:

- **None** — plain shaded colour; not recoloured in-game.
- **Remap 1 (main colour)** — recoloured by the ride's main colour.
- **Remap 2 (secondary)** — recoloured by the secondary colour.
- **Remap 3 (tertiary)** — recoloured by the tertiary colour.
- **Greyscale** — greyscale shading region.
- **Peep** — rider/peep region.

For a remappable material the diffuse colour is *replaced* by the player's chosen
colour in-game, but it still drives the greyscale shading, so a **mid-grey** reads
best as the authored colour. Material region can also be driven by **material
name** in authored `.mtl` files (`_Remap1_`, `_Remap2_`, `_Remap3_` substrings) —
the panel is the equivalent for scene-authored materials.

#### Shading

> Walkthrough: [Tutorial → Material Appearance: Color & Shininess](blender-plugin-tutorial.md#material-appearance-color--shininess).

These map straight onto the renderer's Phong material — what you set is what you
get. There is no metallic/roughness here; the renderer is pure Phong.

| Field | Property | Default | Notes |
|---|---|---|---|
| **Override Color** | `use_color_override` | **off** | Use the **Color** below instead of the shader's Base Color. |
| **Color** | `diffuse_color` | `(0.8, 0.8, 0.8)` | Flat diffuse colour, used only when **Override Color** is on. Enabled only then. |
| **Specular Exponent** | `specular_exponent` | `50.0` | Phong exponent — *tightness* of the highlight. Low = broad, soft sheen; high = tight, glossy hotspot (≥ 1). |
| **Specular Intensity** | `specular_intensity` | `0.5` | *Brightness* of the highlight; scales the specular colour (≥ 0). `0` = fully matte (wood, fabric); raise for plastic/metal/glass. |
| **Tint Highlight** | `use_specular_tint` | **off** | Tint the highlight with **Specular Tint** instead of white. |
| **Specular Tint** | `specular_tint` | `(1, 1, 1)` | Highlight colour, used only when **Tint Highlight** is on. Enabled only then. E.g. a warm tint for brass/gold. |

**Diffuse colour resolution:**

- If **Override Color** is on → the panel's **Color** is used.
- Otherwise → the material's **Principled BSDF Base Color** is used (so the
  Blender viewport still previews the surface). *Never* the bpy material's
  `diffuse_color` viewport swatch, which defaults to 0.8 grey and would make
  everything render grey.

**Specular** is *always* taken from this panel, never from the shader. So:

- **Shiny chrome rail:** high Specular Intensity, high Specular Exponent.
- **Matte wooden body:** Specular Intensity `0` (exponent then doesn't matter).
- **Brass/gold:** raise intensity, turn on **Tint Highlight**, set a warm tint.

**Textures:** you can paint a surface either by plugging an Image Texture node
into the Principled BSDF **Base Color**, or by setting the add-on's explicit
**Texture** pointer. The explicit Texture wins if both are present. On-disk images
load directly; packed/generated images are materialised to a temp PNG first.

---

## Quick map: UI → output

| UI control | Goes to |
|---|---|
| Identity fields | `object.json` header (id, name, authors, version, …) |
| Ride Type | `ride_type` (selects built-in track sprites) |
| Scale / Units per Tile | `units_per_tile` (sprite size + position conversions) |
| Sprite groups | `sprites` (which rotation tables are rendered) |
| Train + Ride Flags | train limits, `zero_cars`, sounds, ride flags |
| Default Colours | `default_colors` build-menu presets |
| Car Types | `vehicles[]` entries + `configuration` slot map |
| Custom Lighting | the render light rig (replaces the default) |
| Object **Role** | sorts the mesh into body / restraint / rider arrays |
| **Rider Number** | seat-row pairing + left/right remap auto-assignment |
| Restraint Swing / keyframes | the 4-frame restraint `orientation` animation |
| Material **Region** + flags | `Material.region` / `Material.flags` bits |
| **Shading** fields | `Material.color` / `specular_color` / `specular_exponent` |
