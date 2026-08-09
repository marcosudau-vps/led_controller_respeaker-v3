"""What both ends of the wire have to agree on, and nothing else.

Small on purpose, and free of dependencies on purpose. The route prefix is not
the server's property — a client that cannot name it cannot call anything — so
keeping it in the server module made the HTTP *client* import FastAPI, Starlette
and Pydantic to learn a seven-character string. In a frozen build that is the
whole server stack in the binary of an application that never serves.

Anything else the two sides must agree on before they can talk belongs here too.
Anything only one of them needs does not.
"""

from __future__ import annotations

API_PREFIX = "/api/v3"
"""The only route prefix there is. No compatibility route, by design."""


__all__ = ["API_PREFIX"]
