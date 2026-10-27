"""Re-export from the canonical ``metis.library.extraction``.

The implementation moved to ``metis.library.extraction``. This module keeps the
``metis.library.graders._extraction`` import path working.
"""

from metis.library.extraction import (
    ExtractionError as ExtractionError,
)
from metis.library.extraction import (
    ExtractionResult as ExtractionResult,
)
from metis.library.extraction import (
    extract_content as extract_content,
)
