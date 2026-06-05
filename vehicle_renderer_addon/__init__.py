"""OpenRCT2 Vehicle Generator: Blender add-on entry point.

Registration order matters: PropertyGroups (and their Scene/Object/Material
pointer properties) must exist before the panels that draw them. The renderer
itself lives in the bundled `openrct2_vehicle_generator` wheel; this package is
only the UI + scene adapter.
"""

from . import operators, panels, props


def register():
    props.register()
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
    props.unregister()
