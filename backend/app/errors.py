"""The one error type services raise when a product rule says no.

Services never import FastAPI. They raise RuleError with a plain-English
message and a status code, and a single handler in main.py turns it into an
HTTP response. That keeps try/except out of every route.
"""


class RuleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
