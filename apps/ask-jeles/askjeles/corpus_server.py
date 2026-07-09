"""Standalone MCP server over AskJeles' own verified-nugget corpus.

Mirrors willow-mcp's shape — FastMCP, stdio by default, every tool takes an
`app_id` — but scoped to one small corpus so it can run independently of
any particular fleet and be MCP-agnostic: any stdio MCP client (Claude
Code, Claude Desktop, Cursor, willow-mcp itself, a bare script) can point
at it with `python -m askjeles.corpus_server`.

Unlike willow-mcp, this server does not implement manifest-based ACL — the
corpus is already scoped to a single app's own data, so there is nothing
for a permission gate to isolate. `app_id` is accepted on every tool for
naming-convention parity and so a future gate can be added without
changing the tool signatures.

Tools:
  corpus_ask     — best-match nugget for a question, or {found: false}
                   (logs a gap on miss)
  corpus_search  — ranked nugget search (no gap logging)
  corpus_get     — fetch a single nugget by id
  corpus_list    — list nuggets, most recently updated first
  corpus_put     — add or update a verified nugget
  corpus_gaps    — list logged "I don't know yet" questions
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from askjeles import corpus, willow_mcp_client

mcp = FastMCP(
    "askjeles-corpus",
    instructions=(
        "AskJeles' verified-nugget corpus. Ask a question to get a cited, "
        "human-verified answer if one exists, search the corpus directly, "
        "or contribute a new verified nugget. Misses are logged as gaps "
        "for someone to fill in later."
    ),
)


@mcp.tool()
def corpus_ask(app_id: str, question: str) -> dict:
    """Answer from the verified corpus if a nugget matches; returns
    {found: false} and logs a gap otherwise. The gap also gets a
    best-effort, non-blocking forward to willow-mcp's fleet-wide gap
    backlog, so it isn't just a local-to-ask-jeles secret."""
    result = corpus.ask_corpus(question)
    if not result.get("found"):
        willow_mcp_client.forward_gap(question)
    return result


@mcp.tool()
def corpus_search(app_id: str, query: str, limit: int = 8) -> list:
    """Ranked nugget search across the corpus. Never logs a gap."""
    return corpus.search_nuggets(query, limit=limit)


@mcp.tool()
def corpus_get(app_id: str, nugget_id: str) -> dict:
    """Fetch a single nugget by id."""
    return corpus.get_nugget(nugget_id)


@mcp.tool()
def corpus_list(app_id: str, limit: int = 50) -> list:
    """List nuggets, most recently updated first."""
    return corpus.list_nuggets(limit=limit)


@mcp.tool()
def corpus_put(
    app_id: str,
    question: str,
    answer: str,
    sources: list[str],
    verified_by: str,
    tags: Optional[list[str]] = None,
    nugget_id: Optional[str] = None,
) -> dict:
    """Add or update a verified nugget. Requires question, answer, at least
    one source, and who verified it. Returns {id, action}."""
    return corpus.put_nugget(
        question, answer, sources, verified_by, tags=tags, nugget_id=nugget_id
    )


@mcp.tool()
def corpus_gaps(app_id: str, limit: int = 50) -> list:
    """List logged 'I don't know yet' questions, most-asked first — the
    corpus's growth queue."""
    return corpus.list_gaps(limit=limit)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
