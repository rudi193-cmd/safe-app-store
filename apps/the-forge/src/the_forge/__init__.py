"""The Forge — SAFE-native, multi-tenant app-building playground.

DESIGN-PHASE SCAFFOLD. No builder functionality is implemented yet. This
package exists so the design (docs/design/the-forge.md, D1-D13) has a real
home to grow into, built import-pure from the first commit per D13: nothing
in here imports `safe-app-store` internals directly, and nothing outside
this package should need to import back into it either, once there's
something here worth importing.

See docs/design/the-forge.md for the actual architecture. This module will
lag it until decisions turn into code — check the design doc, not this
docstring, for what's actually true.
"""

__version__ = "0.1.0"
