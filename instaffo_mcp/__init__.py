"""Instaffo MCP server.

An MCP server that gives an AI assistant access to a candidate's own Instaffo
account, authenticated with the candidate's own browser session.

Architecture note: the domain tools (matches, jobs, messaging, profile) are
deliberately NOT implemented yet. Whether they should replay Instaffo's JSON
API or drive the page with a browser is decided by one observation of the app's
network traffic, which the capture harness in this package produces. See README.
"""

__version__ = "0.1.0"
