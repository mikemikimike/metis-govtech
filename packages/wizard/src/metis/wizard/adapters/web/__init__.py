"""The wizard-local web door.

`server.py` is the transport and `store.py` is the directory of sessions; the frontend it
serves is built into `static/`. Nothing in the shared layers imports this package, and nothing
here imports the CLI — the door is removable, and deleting it leaves a working terminal wizard
behind.

FastAPI arrives through the package's `web` extra rather than its base dependencies, so a
CLI-only install carries no web framework. Importing this module is asking for one.
"""
