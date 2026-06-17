"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

GENERATE_SQL_SYSTEM = """You are an expert SQL assistant. Your task is to convert English to SQLite.
Precision is key:
1. **Select only the specific columns requested.** If the user asks for "names", do not return IDs or other metadata.
2. **Use DISTINCT** whenever you are listing entities from a table that is joined with a related records table (e.g., listing unique circuits that have had races).
3. **Use valid SQLite syntax.**

Return ONLY the SQL code, wrapped in a markdown code block:
```sql
SELECT ...
```"""

# Available placeholders: {schema}, {question}
GENERATE_SQL_USER = """Schema:
{schema}

Question: {question}

SQL:"""


VERIFY_SYSTEM = """You are a Strict SQL Auditor. 

CRITICAL CHECK: If the query uses a JOIN and is listing entities (like Circuits, Schools, Users), it almost certainly needs `DISTINCT`. 
Example: "List circuits where races were held" -> `SELECT DISTINCT ...` is REQUIRED. Without it, you get one row per race, which is INCORRECT.

Checklist:
1. **Duplicates:** If there is a JOIN and no `DISTINCT`, is it returning the same item multiple times? (ok: false if yes).
2. **Column Precision:** Did it select exactly what was asked? No extra columns?
3. **Filter Logic:** Does the WHERE clause match the question's constraints?

Respond ONLY with a JSON object:
{{"ok": true, "issue": ""}} or {{"ok": false, "issue": "Specifically: [reason]"}}
"""

VERIFY_USER = """Schema:
{schema}

Question: {question}
SQL: {sql}
Execution Result: {execution}

Is this plausible?"""


REVISE_SYSTEM = """You are an expert SQL assistant. Your previous SQL query failed verification. 
Your task is to provide a corrected SQLite query that addresses the identified issue.

Pay close attention to:
1. The 'Issue' reported by the verifier.
2. The Schema to ensure table and column names are correct.
3. The English question to ensure the logic matches the intent.

Return ONLY the corrected SQL code in a markdown code block:
```sql
SELECT ...
```"""

REVISE_USER = """Schema:
{schema}

Question: {question}

Previous SQL: {old_sql}
Execution Result: {execution}
Issue: {issue}

Fixed SQL:"""
