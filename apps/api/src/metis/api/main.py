from fastapi import FastAPI
from metis.api import __version__, core_version

app = FastAPI(title="METIS API", version=__version__)


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "core_version": core_version}
