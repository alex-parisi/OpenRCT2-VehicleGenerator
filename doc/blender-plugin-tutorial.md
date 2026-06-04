# OpenRCT2-VehicleGenerator Blender Plugin Tutorial

After [installing the plugin](blender-plugin-installation.md), you can follow this tutorial 
to generate a very basic vehicle for the Classic Wooden Roller Coaster from RCT1.

> Looking for an exhaustive, lever-by-lever description of every UI control
> rather than a walkthrough? See the [add-on reference](blender-plugin-reference.md).

**NOTE**: This tutorial assumes you have the RCT1 assets installed in OpenRCT2. If you do 
not, use another similar ride that you do have the assets for.

Peep model is borrowed from X7's [RCTGen](https://github.com/X123M3-256/RCTGen) project.

The vehicle model and restraint model are built procedurally using 
[build_wooden_car.py](../scripts/build_wooden_car.py) and 
[build_wooden_restraint.py](../scripts/build_wooden_restraint.py)

## Download the Example files

You'll need all the files in [examples/wooden](../examples/wooden), except `classic_wooden.yaml`. 

Download or clone the repo so that you have these files handy.

Or, you can use your own object/material files, but you're on your own :)

## Vehicle Body

### Open Blender and Import the Car Object

Start with a completely empty scene: no objects, no cameras, no lights.

**Import the `car.obj` file:**

File --> Import --> Wavefront

<img src="_static/import-obj.png" width="400">

**Then select the `car.obj` file:**

<img src="_static/car-obj.png" width="400">

<img src="_static/car-mesh.png" width="400">

### Assign "Body" Role to Car

> Reference: [Selected Object → Role](blender-plugin-reference.md#role).

After importing the object, all the meshes should be still be selected. In the 3D viewport, 
press **N** to open the sidebar and click the **OpenRCT2** tab. The active object's settings 
live in the **"Selected Object"** section there. Select the "Body" role.

> Everything for the vehicle is authored from this **OpenRCT2** sidebar tab: the
> ride-wide settings up top ("OpenRCT2 Vehicle") and the active object's role,
> materials, etc. in "Selected Object" below it. No need to leave the viewport.

<img src="_static/body-role.png" width="300">

Then, right click on the "Body" role, and press "Copy to Selected" to ensure that all of the 
car meshes have the "Body" role.

<img src="_static/copy-to-selected.png" width="300">

All meshes associated with the vehicle car need to get assigned this role.

### Assign Color Remap Meshes

> Reference: [Materials → Region & flags](blender-plugin-reference.md#region--flags).

Material settings live in the **"Selected Object"** section of the OpenRCT2
sidebar tab, the same place you set an object's role, so you don't have to
switch tabs. If an object has more than one material, pick which one to edit
from the slot list in that section.

In the current example, the vehicle "car" is Remap1, the seat backs are Remap2, and the trucks 
(underside of the vehicle) are Remap3. The wheels are assigned the "Wheel" material which is not 
used, and leaves them as the color they're currently rendering at.

When recoloring a train in OpenRCT2, the first color picker dropdown corresponds to the meshes 
assigned Remap1, and so on. This allows you to control which surfaces get recolored.

Select the car, and in the sidebar's "Selected Object" --> "Materials" section, set the 
"Region" to "Remap 1".

Do the same for the seat backs, and assign them to "Remap 2".

Finally, do the same for the trucks beneath the car (not the wheels though!), and assign them 
"Remap 3".

If you are using existing materials, just ensure that the material name includes "_Remap1_" in 
the name at some point if you want meshes assigned that material to be remapped to region 1. Do 
the same for "_Remap2_" and "_Remap3_".

Feel free to change them how you like.

### Material Appearance: Color & Shininess

> Reference: [Materials → Shading](blender-plugin-reference.md#shading).

A material's look is controlled directly in the **OpenRCT2 Vehicle** section of
the OpenRCT2 sidebar tab's "Selected Object" section, under **Shading**. These map straight onto the
renderer's settings, so what you set is what you get.

- **Color** sets the flat surface colour. By default, it's read from the
  shader's **Base Color** (so the Blender viewport still previews it). Tick
  **Override Color** to set it explicitly here instead. (For a remappable region
  the colour is ignored in-game and replaced by the player's chosen colour, but
  it still drives the greyscale shading, so a mid-grey reads best.) You can also
  plug an **Image Texture** node into Base Color, or use the add-on's explicit
  Texture field, to paint the surface.
- **Specular Intensity** controls how bright the highlight is. `0` is fully
  matte (wood, fabric); raise it for glossier surfaces (plastic, metal, glass).
- **Specular Exponent** controls how sharp the highlight is (the Phong
  exponent). Low values give a broad, soft sheen; high values give a tight,
  glossy hotspot (polished metal).
- **Tint Highlight** (optional) tints the highlight with a colour instead of
  white (e.g. a warm tint for brass or gold). Leave it off for normal metals and
  dielectrics, where the highlight is white.

So to make a shiny chrome rail: high Specular Intensity, high Specular Exponent.
For a matte wooden body: low Specular Intensity.

### Checklist

- All meshes assigned to the "Body" role in the "OpenRCT2 Vehicle" section of the "Objects" tab
- Remap materials assigned to respective meshes

## Riders

> Reference: [Selected Object → Role: Rider seat](blender-plugin-reference.md#role-rider-seat).

### Import the Peep Object

Just like `car.obj`, import `peep.obj` into the Scene.

While it's highlighted, open the "Object" panel, and assign it the "Rider set" role.

First, move the peep into the top-left seat of the car. About here should do it:

<img src="_static/peep-placement-1.png" width="500">

Then, copy and paste this peep model into the other seats. You can do this by selecting 
the peep model, then pressing Shift+D, and then Esc. Then use the move tool to move the copied 
mesh. 

<img src="_static/peep-placement-2.png" width="500">

Ensure all the peep meshes are assigned the "Rider set" role.

Each peep also has a **Rider Number** field in the Object panel. The exporter sorts 
peeps by this number and pairs them into seat rows: numbers 0 and 1 form the first row, 
2 and 3 form the second, and so on. For the 2x2 wooden car above, set the two front-row 
peeps to 0 and 1, and the two back-row peeps to 2 and 3. OpenRCT2 only supports pairs of 
riders per row (or a single rider for one-seat cars).

### Assign Color Remap Meshes

The peep's recolorable material (e.g. the shirt) just needs to be marked as a remappable 
region so it keeps the rider's colour when boarding. You **don't** have to pick Remap1 vs 
Remap2 per seat yourself, and the exporter assigns those automatically from each peep's position 
in its seat row: the **left** peep (the lower Rider Number in the pair) gets Remap1, and the 
**right** peep gets Remap2. So you can set the shirt material to "Remap 1" on every peep (or 
just leave the model's existing remappable shirt material as-is) and the sides sort themselves 
out.

Click a peep, and in the sidebar's "Selected Object" --> "Materials" section pick its shirt 
material slot and set the "Region" to any remappable region ("Remap 1" is fine for all of them).

<img src="_static/peep-remap-1.png" width="600">

Only materials you mark remappable are touched. Skin, hair, and shoes are left alone. If you 
deliberately want a peep's accent to follow the ride's **tertiary** colour, set that material 
to "Remap 3": Remap3 is preserved and never overwritten by the left/right auto-assignment.

### Checklist

- Place the peep model(s) in the seats you want peeps to sit at in-game.
- Assign the peep mesh to the "Rider seat" role
- Set each peep's "Rider Number" so that the two peeps sharing a row get consecutive values (0/1 for the first row, 2/3 for the second, etc.)
- Mark the peep's shirt material as a remappable region

## Restraint

> Reference: [Selected Object → Role: Restraint](blender-plugin-reference.md#role-restraint).

### Import the Restraint Object

Just like `car.obj` and `peep.obj`, import `restraint.obj` into the Scene.

While it's highlighted, open the "Object" panel, and assign it the "Restraint" role.
For this example, you can leave the pivot value set to 90 degrees.

They key thing to remember here is that the restraint meshes will pivot around their origin.
In the example restraint, you can see the origin for all the restraint meshes is a good pivot 
point:

<img src="_static/restraint-pivot.png" width="400">

Copy these meshes and put a restraint for the back row as well:

<img src="_static/restraints.png" width="400">

### Animation: Swing degrees vs. keyframes

The Restraint role panel exposes two ways to drive the 4-frame restraint animation
OpenRCT2 expects:

- **Restraint Swing** (degrees): the simple path. The add-on linearly
  interpolates the bar from 0° to your value across the 4 frames, swinging
  around the object's origin. Good enough for a classic lap bar.
- **Keyframes on the restraint object's transform**: for anything more
  expressive. If the restraint object has *any* keyframes (rotation,
  translation, or both), the add-on samples its world transform at 4
  evenly-spaced scene frames between `Anim Start Frame` and `Anim End Frame`
  (also on the Restraint panel) and ignores the Swing value. This lets you
  use Blender's graph editor for easing, multi-axis swings, shoulder bars
  that drop *then* slide forward, etc. You can also scrub the timeline
  in Blender to preview the motion before rendering.

Set the rest-pose keyframe at `Anim Start Frame`; the mesh is extracted at
that frame, so whatever orientation the restraint has there becomes frame 0
of the animation.

### Checklist

- Ensure all restraint meshes are assigned the "Restraint" role.
- Ensure that the origin for all the restraint meshes is the central pivot point.
- If you keyframed the restraint, set `Anim Start Frame` / `Anim End Frame`
  to the timeline range that contains your animation.

## Multiple Car Types

> Reference: [OpenRCT2 Vehicle → Car Types](blender-plugin-reference.md#car-types).

Everything so far builds **one** car from the whole scene. That's the simplest
case, and all that most rides need. But a train can mix several *car-type variants*: a
distinct **front** (head/engine) car, a **rear** (tail) car, and the **default**
car used for everything in between. Each variant becomes its own entry in the
exported object, and OpenRCT2 picks which one to draw at each position in the
train.

If you only want a single car for the whole train, skip this section: with no
car types defined the add-on renders the entire scene as the one default car
(what the tutorial built above).

### Put each variant in its own Collection

A car type's geometry comes from a Blender **Collection**, not the whole scene.
So to author variants, put each one's objects (body, riders, restraints) in a
separate collection (e.g. `Default Car`, `Front Car`, `Rear Car`). In the
Outliner, select a variant's objects and press **M** to move them into a new
collection.

The roles, rider numbers, materials, and restraint setup are authored exactly
the same way inside each collection. A collection is just the bag of objects
that make up one car.

### Add the car types

In the **OpenRCT2 Vehicle** sidebar tab, find the **Car Types** panel. Use the
**+** button to add one entry per variant, and for each:

- **Collection**: point it at that variant's collection.
- **Slot**: which position in the train this car fills: **Default**, **Front
  (head car)**, or **Rear (tail car)**. You need at least one car type in the
  **Default** slot; Front and Rear are optional. Slots are unique. Assigning a
  slot already held by another car type clears it from the other.
- **Mass**, **Spacing**, **Draw Order**, **Effect Visual**, and the per-type
  **Vehicle Flags**: set per variant (a heavy engine vs. light cars, etc.).

### Collection Offset: stage variants without overlap

> Reference: [Car Types → Collection Offset, in detail](blender-plugin-reference.md#collection-offset-in-detail).

If you build several collections in the same scene, their geometry will pile up
on top of each other at the origin, which is awkward to author. To avoid that,
just **move a collection aside** in the viewport (select its objects, grab, and
translate). Then record that *same translation* in the car type's **Collection
Offset** field.

The offset is subtracted back out at export, so the car still renders centred;
the field exists purely to let you spread the variants out in the viewport. Enter
the exact X/Y/Z you moved the collection by (in Blender units). For example, if
you shifted the Front Car collection `+5` along X to get it out of the way, set
its Collection Offset to `(5, 0, 0)`.

> Collection Offset only undoes a **rigid move** of the whole collection: the
> translation you applied to slide it aside. Don't *rotate* or *scale* a
> collection as a whole expecting the offset to cancel it; only the move is
> compensated. Leave it at `(0, 0, 0)` (the default) when a collection is already
> modelled at the origin.

### Checklist

- Each car-type variant's objects live in their own Collection.
- One entry per variant in the **Car Types** panel, each pointing at its
  Collection.
- At least one car type assigned to the **Default** slot.
- If you moved a collection aside in the viewport, its **Collection Offset**
  matches that translation.

## Plugin Usage

### Settings

> Reference: [Panel: OpenRCT2 Vehicle (ride-wide)](blender-plugin-reference.md#panel-openrct2-vehicle-ride-wide), and the [Train](blender-plugin-reference.md#train) section for the fields below.

Now, press "N", and then select "OpenRCT2" on the right side.

We'll be using most of the information in the [classic_wodden.yaml](../examples/wooden/classic_wooden.yaml)
file, which is based on the original wooden vehicle json file [here](https://github.com/OpenRCT2/objects/blob/master/objects/rct1/ride/rct1.ride.wooden_rc_trains/object.json)

<img src="_static/plugin-settings.png" width="400">

It is HIGHLY recommended to use settings for a vanilla ride that uses the track-type 
you are targeting. Settings like "Build Menu Priority", "Draw Order", and "Effect Visual" 
are hard to figure out and can lead to glitchy cars if not properly set. Explore the 
[objects](https://github.com/OpenRCT2/objects) repo for vehicle types.

Under the **Train** section you can set "Min Cars / Train" and "Max Cars / Train", 
which control how many cars a train can have. The **Zero Cars** field sets how many 
cars at the *front* of the train carry no riders, like engines, decorative locomotives, or 
leading dummy cars. Those cars are still rendered as part of the train, but the engine 
won't seat any peeps in them. Leave it at `0` (the default) for a train where every car 
holds riders.

### Render Preview

> Reference: [the Test Render / Export buttons](blender-plugin-reference.md#where-the-ui-lives).

We're now ready to see how it would look in-game!

In the top bar, click the "UV Editing". A new window should appear side-by-side with the 
layout window. Ensure that "Show Gizmo" and "Show Overlays" are disabled:

<img src="_static/uv-settings.png" width="200">

Back in the OpenRCT2 Vehicle plugin, scroll down and press "Test Render".

You should see a preview of the car!

<img src="_static/test-render.png" width="600">

### Export

Press the "Export .parkobj" button at the bottom, and save the file to a known location.

## Installing & Using In-Game

Drag-and-Drop (or copy) the `.parkobj` file to the OpenRCT2 object folder. On macOS, this 
will be `~/Library/Application\ Support/OpenRCT2/object`.

Launch the game, and it should be available as an option in the Object Selection menu.

I recommend having a scenario with every ride type enabled, so this way you can create a new 
game, immediately open the Object Selection menu, and see _only_ the new vehicle you added.

Build the targeted ride, select your new vehicle, and give it a test. Make sure everything 
looks as expected!

<img src="_static/in-game.gif" width="600">