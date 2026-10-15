"""Paths shared by directory and ZIP exports, relative to the experiment root."""

from pathlib import PurePosixPath

INPUTS = PurePosixPath("inputs")
OUTPUTS = PurePosixPath("outputs")
INTERVIEW_STATE = INPUTS / "interview_state.json"
SPECIFICATION = OUTPUTS / "specification.yaml"
FIXTURES = OUTPUTS / "fixtures"
REVIEW = OUTPUTS / "review.md"
