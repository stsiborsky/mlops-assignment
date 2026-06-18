curl http://195.242.29.176:8000/v1/chat/completions \
   -H "Content-Type: application/json" \
        -d '{
  "model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
  "messages": [
    {
      "role": "system",
      "content": "You are a SQL expert. Output only the SQL query inside ```sql blocks."
    },
    {
      "role": "user",
      "content": "Database: formula_1\nQuestion: What is the coordinates location of the circuits for Australian grand prix?"
    }
  ],
  "temperature": 0
}'