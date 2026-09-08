"""themes/ — pluggable deck renderers.

`studio` ships as the default and is the only backend a public checkout
needs; the private BH-SEOUL engine in `engine/` is optional and absent from
most checkouts.

To write your own, copy `studio.py` and read `README.md` — the contract is a
`THEMES` tuple plus `render(slides, pptx_path)`.
"""
from . import studio

__all__ = ["studio"]
