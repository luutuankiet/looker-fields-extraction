"""Generated FieldRecord package - re-exports the generated type.

The package boundary keeps generated code (types.py) cleanly separated from
hand-edited code. Consumers import the symbol through schema.py:

    from looker_fields.schema import FieldRecord
"""

from .types import FieldRecord

__all__ = ["FieldRecord"]
