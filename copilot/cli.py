"""CLI REPL for the Reckon copilot -- demo surface."""

import json
import os
import sys

import anthropic

# Use REFERENCE_DATE for the copilot's "today" so date-windowed queries
# align with the frozen demo data. Falls back to real date if unset.
REFERENCE_DATE = os.getenv("REFERENCE_DATE", "2026-07-16")

from copilot.db import get_conn
from copilot.tools import (
    tool_call_funnel,
    tool_check_freshness,
    tool_describe_schema,
    tool_job_completion,
    tool_query_marts,
    tool_revenue_summary,
)

MODEL = "claude-sonnet-4-6"

def _system_prompt() -> str:
    today = REFERENCE_DATE[:10]  # YYYY-MM-DD portion
    return (
        f"Today's date is {today}. "
        "You are a business intelligence copilot for a home-services company. "
        "You answer questions using ONLY the data returned by your tools. "
        "Every number in your answer must come from a tool result. "
        "If a tool returns a 'data_stale' error, relay the refusal message "
        "to the user exactly -- do not guess or estimate. "
        "If a tool returns a 'caveat' field, include that caveat in your answer. "
        "If the data cannot answer the question, say so honestly. "
        "Do not invent, estimate, or hallucinate any numbers."
    )

TOOLS = [
    {
        "name": "check_freshness",
        "description": (
            "Check how recent the warehouse data is. Returns the last load "
            "time and freshness status for each data source."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "revenue_summary",
        "description": (
            "Get revenue data from Stripe payments. Returns revenue_dollars, "
            "net_revenue_dollars, transaction_count, avg_ticket_dollars."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD), optional.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD), optional.",
                },
                "group_by": {
                    "type": "string",
                    "enum": ["service", "date"],
                    "description": "Group by 'service' or 'date', or omit for summary.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "call_funnel",
        "description": (
            "Get call funnel metrics from Aria voice agent data. Returns "
            "total_calls, booked, booking_rate_pct, avg_sentiment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD), optional.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD), optional.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "job_completion",
        "description": (
            "Get job completion metrics by service category. Returns "
            "total_jobs, completed, completion_rate_pct, total_completed_value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_category": {
                    "type": "string",
                    "description": "Filter by service type, optional.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "query_marts",
        "description": (
            "Run a read-only SQL query against the marts tables. Use only "
            "when the other tools cannot answer. Must be a single SELECT "
            "referencing only marts.mart_call_funnel, marts.mart_revenue, "
            "or marts.mart_jobs. Max 100 rows, 5s timeout."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SELECT query against marts tables.",
                },
            },
            "required": ["sql"],
        },
    },
    {
        "name": "describe_schema",
        "description": (
            "Get the schema of all available mart tables. Returns table names, "
            "column names, types, and descriptions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def _dispatch(tool_name: str, tool_input: dict) -> dict:
    """Call the appropriate tool function and return its result."""
    admin_conn = get_conn(read_only=False)
    reader_conn = get_conn(read_only=True)
    freshness_cache: dict = {}

    try:
        if tool_name == "check_freshness":
            return tool_check_freshness(admin_conn)
        elif tool_name == "revenue_summary":
            return tool_revenue_summary(
                admin_conn, reader_conn,
                tool_input.get("date_from"),
                tool_input.get("date_to"),
                tool_input.get("group_by"),
                freshness_cache,
            )
        elif tool_name == "call_funnel":
            return tool_call_funnel(
                admin_conn, reader_conn,
                tool_input.get("date_from"),
                tool_input.get("date_to"),
                freshness_cache,
            )
        elif tool_name == "job_completion":
            return tool_job_completion(
                admin_conn, reader_conn,
                tool_input.get("service_category"),
                freshness_cache,
            )
        elif tool_name == "query_marts":
            return tool_query_marts(
                admin_conn, reader_conn,
                tool_input["sql"],
                freshness_cache,
            )
        elif tool_name == "describe_schema":
            return tool_describe_schema()
        else:
            return {"error": "unknown_tool", "message": f"Unknown tool: {tool_name}"}
    finally:
        admin_conn.close()
        reader_conn.close()


def ask(client: anthropic.Anthropic, question: str) -> None:
    """Send a question through the copilot and print the grounded answer."""
    messages = [{"role": "user", "content": question}]

    print(f"\n{'=' * 60}")
    print(f"Question: {question}")
    print(f"{'=' * 60}")

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=_system_prompt(),
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"\n  Tool: {block.name}")
                    print(f"  Input: {json.dumps(block.input, default=str)}")

                    result = _dispatch(block.name, block.input)

                    if "sql" in result:
                        print(f"  SQL: {result['sql']}")
                    if "data" in result:
                        print(f"  Rows: {result['row_count']}")
                    if "error" in result:
                        print(f"  Error: {result['message']}")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            print(f"\n{'- ' * 30}")
            print("Answer:")
            for block in response.content:
                if hasattr(block, "text"):
                    print(block.text)
            print()
            break


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is required.")
        print("Set it in your .env file or export it in your shell.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print("Reckon Copilot (type 'quit' to exit)")
    print("Ask questions about revenue, calls, jobs, and data freshness.")
    print()

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        try:
            ask(client, question)
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
