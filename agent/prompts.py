"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

GENERATE_SQL_SYSTEM = """You are an expert SQL assistant. Your task is to convert a natural language question into a valid SQLite query based on the provided schema.
Always return only the SQL code, wrapped in a markdown code block:
```sql
SELECT ...
```
Do not include any other text."""

# Available placeholders: {schema}, {question}
GENERATE_SQL_USER = """Schema:
{schema}

Question: {question}

SQL:"""


VERIFY_SYSTEM = """You are a SQL quality assurance agent. Your task is to determine if the given SQL execution result plausibly answers the user's question.
Check for:
1. SQL errors.
2. Zero results when results are expected.
3. Column names or values that don't match the question's intent.

Respond ONLY with a JSON object:
{{"ok": true, "issue": ""}}  -- if the result is plausible
{{"ok": false, "issue": "detailed explanation of what is wrong"}} -- if not plausible
"""

VERIFY_USER = """Question: {question}
SQL: {sql}
Execution Result: {execution}

Is this plausible?"""


REVISE_SYSTEM = """You are an expert SQL assistant. You need to fix a SQL query that failed verification.
Analyze the previous attempt, the execution result, and the reported issue to provide a corrected SQL query.
Always return only the SQL code, wrapped in a markdown code block:
```sql
SELECT ...
```
Do not include any other text."""

REVISE_USER = """Schema:
{schema}

Question: {question}

Previous SQL: {old_sql}
Execution Result: {execution}
Issue: {issue}

Fixed SQL:"""
