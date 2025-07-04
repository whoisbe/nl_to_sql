"""
NL-to-SQL App powered by Gemini 1.5 Pro
"""
import reflex as rx
import duckdb
import pandas as pd
import os
import json
import httpx  # Import httpx for making API calls
from typing import Any, Dict, List

# --- Local Imports ---
import config

# --- Configuration & Setup ---
# Create data directories if they don't exist
for dir_path in [config.DATABASE_DIR, config.DATA_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

# Dictionary to hold active database connections
_connections: dict[str, duckdb.DuckDBPyConnection] = {}

def get_db_conn(db_name: str) -> duckdb.DuckDBPyConnection | None:
    """Get or create a database connection from the global pool."""
    if not db_name:
        return None
    if db_name not in _connections:
        try:
            db_path = os.path.join(config.DATABASE_DIR, db_name)
            _connections[db_name] = duckdb.connect(database=db_path, read_only=False)
        except Exception as e:
            print(f"Failed to connect to {db_path}: {e}")
            return None
    return _connections[db_name]

class State(rx.State):
    """The application state."""
    chat_history: List[Dict[str, str]] = []
    db_name: str = ""
    is_connected: bool = False
    processing: bool = False
    
    # Gemini API Key state
    api_key: str = ""
    api_key_set: bool = False

    def set_api_key(self, key: str):
        """Store the API key and update the UI."""
        self.api_key = key
        self.api_key_set = bool(key)

    def handle_api_key_submit(self, form_data: dict[str, Any]):
        """Handle the API key form submission."""
        self.set_api_key(form_data["api_key_input"])

    async def handle_submit(self, form_data: dict[str, Any]):
        """Handle the user's query submission."""
        question = form_data["question"]
        if not question.strip() or self.processing:
            return

        self.chat_history.append({"role": "user", "text": question})
        yield
        
        if not self.is_connected:
            if question.lower().startswith("connect to "):
                db_file = question[len("connect to "):].strip()
                if not db_file.endswith(".duckdb"):
                    db_file += ".duckdb"
                self.connect_to_db(db_file)
            else:
                self.chat_history.append({"role": "system", "text": "Please connect to a database first. Use 'connect to <database_name>'."})
        else:
            async for _ in self.process_query_with_gemini(question):
                pass

    def connect_to_db(self, db_file: str):
        """Establish a connection to a DuckDB database."""
        conn = get_db_conn(db_file)
        if conn:
            self.db_name = db_file
            self.is_connected = True
            self.chat_history.append({"role": "system", "text": f"Successfully connected to {self.db_name}."})
            self.show_all_tables()
        else:
            self.chat_history.append({"role": "system", "text": f"Failed to connect to database: {db_file}"})

    def get_db_schema(self) -> str:
        """Get the database schema as a string for the LLM prompt."""
        conn = get_db_conn(self.db_name)
        if not conn:
            return "No database connection."
        
        try:
            tables = conn.execute("SHOW TABLES;").fetchall()
            schema = ""
            for table_tuple in tables:
                table_name = table_tuple[0]
                schema += f"### Table: {table_name}\n"
                columns = conn.execute(f"PRAGMA table_info('{table_name}');").df()
                schema += columns[['name', 'type']].to_string(index=False) + "\n\n"
            return schema if schema else "No tables in the database."
        except Exception as e:
            return f"Error getting schema: {e}"

    def show_all_tables(self):
        """Display all tables in the current database."""
        conn = get_db_conn(self.db_name)
        if not conn:
            self.chat_history.append({"role": "system", "text": "Database connection lost."})
            return
        
        try:
            tables = conn.execute("SHOW TABLES;").fetchall()
            if tables:
                table_list = "\n".join([f"- {table[0]}" for table in tables])
                response = f"Tables in the database:\n{table_list}"
            else:
                response = "No tables found in the database."
            self.chat_history.append({"role": "system", "text": response})
        except Exception as e:
            self.chat_history.append({"role": "system", "text": f"Error getting table info: {e}"})

    def execute_sql(self, sql_query: str):
        """Execute a SQL query and display the results."""
        conn = get_db_conn(self.db_name)
        if not conn:
            self.chat_history.append({"role": "system", "text": "Database connection lost."})
            return
        
        try:
            result = conn.execute(sql_query)
            df = result.df() if result else pd.DataFrame()
            if not df.empty:
                response = df.to_markdown(index=False)
                self.chat_history.append({"role": "system", "text": f"Query Result:\n```\n{response}\n```"})
            else:
                self.chat_history.append({"role": "system", "text": "Query executed successfully, but returned no results."})
        except Exception as e:
            self.chat_history.append({"role": "system", "text": f"Error executing SQL: {e}"})

    def create_table_from_csv(self, file_path: str, table_name: str):
        """Create a DuckDB table from a local CSV file."""
        conn = get_db_conn(self.db_name)
        full_path = os.path.join(config.DATA_DIR, file_path)
        
        if not conn or not os.path.exists(full_path):
            self.chat_history.append({"role": "system", "text": f"Error: File not found at '{full_path}' or no DB connection."})
            return
            
        try:
            query = f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{full_path}');"
            conn.execute(query)
            self.chat_history.append({"role": "system", "text": f"Successfully created table '{table_name}' from '{file_path}'."})
            self.show_all_tables()
        except Exception as e:
            self.chat_history.append({"role": "system", "text": f"Error creating table from CSV: {e}"})

    async def process_query_with_gemini(self, query: str):
        """The core logic to process a query using the Gemini API."""
        self.processing = True
        yield

        schema = self.get_db_schema()
        prompt = f"""You are an expert database assistant. Your job is to interpret a user's request and respond with a single, valid JSON object.

### Instructions
1.  Analyze the user's request and the provided database schema.
2.  Your response MUST be a single JSON object. Do not add any text before or after it.
3.  The JSON object must have an "action" field, which can be either "sql" or "create_table".

### Action Types

#### 1. "sql"
-   Use this for any request that asks a question about the data.
-   The "query" field must contain a single, valid DuckDB SQL query.
-   Only use tables and columns from the provided schema.
-   Example: {{"action": "sql", "query": "SELECT department, AVG(salary) FROM employees GROUP BY department;"}}

#### 2. "create_table"
-   Use this for any request to create a table from a CSV file.
-   The "file_path" field must contain the name of the .csv file.
-   The "table_name" field should be a suitable name for the new table.
-   Example: {{"action": "create_table", "file_path": "members.csv", "table_name": "members"}}

---
### Database Schema
{schema}
---
### User Request
"{query}"

---
Respond with only the JSON object.
"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent?key={self.api_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=60,
                )
            
            if response.status_code != 200:
                error_text = f"API Error: {response.text}"
                self.chat_history.append({"role": "system", "text": error_text})
                return

            response_json = response.json()
            content = response_json["candidates"][0]["content"]["parts"][0]["text"]
            
            # FIX: Robustly find and parse the JSON object from the response.
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start != -1 and json_end != 0:
                json_str = content[json_start:json_end]
                result_json = json.loads(json_str)
            else:
                raise json.JSONDecodeError("No JSON object found in the response", content, 0)

            action = result_json.get("action")

            if action == "sql":
                sql_query = result_json.get("query")
                self.chat_history.append({"role": "system", "text": f"Generated SQL:\n```sql\n{sql_query}\n```"})
                yield
                self.execute_sql(sql_query)
            elif action == "create_table":
                file_path = result_json.get("file_path")
                table_name = result_json.get("table_name")
                self.chat_history.append({"role": "system", "text": f"Executing command: Create table '{table_name}' from '{file_path}'."})
                yield
                self.create_table_from_csv(file_path, table_name)
            else:
                self.chat_history.append({"role": "system", "text": "The model returned an unknown action."})

        except Exception as e:
            self.chat_history.append({"role": "system", "text": f"An error occurred: {e}"})
        finally:
            self.processing = False
            yield

# --- UI Components ---
def qa_pair(data: dict[str, str]) -> rx.Component:
    """A chat pair component."""
    return rx.box(
        rx.box(
            rx.hstack(
                rx.avatar(
                    name=rx.cond(data["role"] == "user", "U", "S"), 
                    size="2"
                ),
                rx.text(
                    rx.cond(data["role"] == "user", "You", "System"),
                    font_weight="bold",
                ),
                align_items="center"
            ),
            rx.markdown(data["text"], component_map={"code": lambda text, **props: rx.code(text, **props, white_space="pre-wrap")}),
            text_align="left",
            padding_y="0.5em"
        ),
        width="100%",
    )

def index() -> rx.Component:
    """The main application UI."""
    return rx.container(
        rx.vstack(
            rx.heading("Natural Language Data Analysis", size="7", padding_bottom="0.5em"),
            rx.cond(
                ~State.api_key_set,
                rx.vstack(
                    rx.text("Please enter your Google AI Studio API key to begin."),
                    rx.form(
                        rx.hstack(
                            rx.input(
                                placeholder="Enter API Key...",
                                id="api_key_input",
                                type="password",
                                flex_grow=1,
                            ),
                            rx.button("Save Key", type="submit"),
                        ),
                        on_submit=State.handle_api_key_submit,
                        width="100%",
                    ),
                    align="center",
                    padding="2em",
                    border=f"1px solid {rx.color('gray', 6)}",
                    border_radius="var(--radius-3)",
                    width="100%",
                    max_width="500px", # Give the API key form a max width
                )
            ),
            rx.box(
                rx.foreach(State.chat_history, qa_pair),
                width="100%",
                height="70vh",
                overflow_y="auto",
                border=f"1px solid {rx.color('gray', 6)}",
                border_radius="var(--radius-3)",
                padding="1rem",
                # Use a slightly different dark background for contrast
                background=rx.color('gray', 2), 
            ),
            rx.form(
                rx.hstack(
                    rx.input(
                        placeholder="Connect to a DB or ask a question...",
                        id="question",
                        flex_grow=1,
                        disabled=State.processing | ~State.api_key_set,
                    ),
                    rx.button("Send", type="submit", is_loading=State.processing, disabled=~State.api_key_set),
                ),
                on_submit=State.handle_submit,
                reset_on_submit=True,
                width="100%",
            ),
            align="center",
            spacing="4",
            width="100%",
            padding_x="2em", # Add horizontal padding for full-width layout
        ),
        # Remove max_width to make the container span the full page
        padding_top="2rem",
        width="100%", 
    )


# Add state and page to the app.
app = rx.App(
    theme=rx.theme(
        # Use a dark appearance for the solarized theme
        appearance="dark",
        has_background=True,
        radius="large",
        # Use a solarized-friendly accent color
        accent_color="cyan",
    )
)
app.add_page(index)

# Create sample CSV files for the user to experiment with.
if not os.path.exists(os.path.join(config.DATA_DIR, 'employees.csv')):
    with open(os.path.join(config.DATA_DIR, 'employees.csv'), 'w') as f:
        f.write("id,first_name,last_name,email,department,salary\n")
        f.write("1,Alice,Smith,alice@web.com,Engineering,100000\n")
        f.write("2,Bob,Jones,bob@web.com,Marketing,80000\n")
        f.write("3,Charlie,Brown,charlie@web.com,Engineering,120000\n")

if not os.path.exists(os.path.join(config.DATA_DIR, 'members.csv')):
    with open(os.path.join(config.DATA_DIR, 'members.csv'), 'w') as f:
        f.write("id,name,join_date,team\n")
        f.write("101,David,2023-01-15,Alpha\n")
        f.write("102,Eve,2023-02-20,Bravo\n")
        f.write("103,Frank,2023-03-10,Alpha\n")
