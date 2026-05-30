## OpenRCT2-VehicleGenerator Blender Plugin Tutorial

After [installing the plugin](blender-plugin-installation.md), you can follow this tutorial 
to generate a very basic vehicle for the Classic Wooden Roller Coaster from RCT1.

**NOTE**: This tutorial assumes you have the RCT1 assets installed in OpenRCT2. If you do 
not, use another similar ride that you do have the assets for.

Peep model is borrowed from X7's [RCTGen](https://github.com/X123M3-256/RCTGen) project.

The vehicle model and restraint model are built procedurally using 
[build_wooden_car.py](../scripts/build_wooden_car.py) and 
[build_wooden_restraint.py](../scripts/build_wooden_restraint.py)

### Download the Example files

You'll need all the files in [examples/wooden](../examples/wooden), except `classic_wooden.yaml`. 

Download or clone the repo so that you have these files handy.

### Open Blender and Import the Car Object

Start with a completely empty scene: no objects, no cameras, no lights.

**Import the `car.obj` file:**

File --> Import --> Wavefront

<img src="_static/import-obj.png" width="400">

**Then select the `car.obj` file:**

<img src="_static/car-obj.png" width="400">

### Assign "Body" Role to Car

After importing the object, all the meshes should be still be selected. While they are all 
selected, go to the "Object Panel" on the right side, and scroll down the "OpenRCT2 Vehicle" 
section. Select the "Body" role.

<img src="_static/body-role.png" width="300">

Then, right click on the "Body" role, and press "Copy to Selected" to ensure that all of the 
car meshes have the "Body" role.

<img src="_static/copy-to-selected.png" width="300">

### Assign Color Remap Meshes

Open the "Material" tab on the right side.

In the current example, the green surfaces are assigned the "Remap1" material, which corresponds 
to the first color picker selection. 

We'll leave these mostly as-is, but select the two seat-backs to change to "Remap2".

Select the two seat-back meshes with shift-click, then 



