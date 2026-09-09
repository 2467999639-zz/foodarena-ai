"""BDD scenario collection for the three core user stories.

Step definitions are registered by the sibling ``conftest.py``; this module
only converts each ``.feature`` scenario into a runnable test.
"""

from __future__ import annotations

from pytest_bdd import scenarios

scenarios("US01_session.feature")
scenarios("US02_debate.feature")
scenarios("US03_report.feature")
