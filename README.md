# Natural Language to SQL with Reflex and Gemini 1.5 Pro

This is a web application built with [Reflex](https://reflex.dev/) that allows you to interact with a [DuckDB](https://duckdb.org/) database using natural language. It leverages the **Gemini 1.5 Pro** API to translate natural language into SQL queries and database commands.

## Project Structure

- `nl_to_sql/`: Main project directory.
- `assets/`: Static files.
- `nl_to_sql/nl_to_sql.py`: The main Reflex application file.
- `nl_to_sql/config.py`: The configuration file for directory paths.  
- `database/`: Directory to store DuckDB database files (created automatically).
- `data/`: Directory for data files like CSVs. Sample `employees.csv` and `members.csv` are provided.
- `rxconfig.py`: Reflex configuration file.
- `README.md`: This file.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd nl_to_sql
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install reflex duckdb pandas httpx
    ```

4.  **Get a Gemini API Key:**
    -   Go to [Google AI Studio](https://aistudio.google.com/).
    -   Click "Get API key" and create a new API key.
    -   Copy the key. You will need to enter this into the application's UI.

5.  **Initialize the Reflex app:**
    ```bash
    reflex init
    ```

## How to Run the Application

1.  **Start the development server:**
    ```bash
    reflex run
    ```

2.  **Open your web browser** and navigate to `http://localhost:3000`.

## How to Use the Application

1.  **Enter your API Key:** When you first open the app, you will be prompted to enter your Gemini API key. Paste your key and click "Save Key".

2.  **Connect to a database:**
    -   The application starts without a database connection.
    -   Type `connect to my_database` to create and connect to `my_database.duckdb`.

3.  **Create tables from CSVs:**
    -   The `data/` folder contains `employees.csv` and `members.csv`.
    -   Type `create a table called employees from the employees.csv file`.
    -   Type `create a table for members from members.csv`.

4.  **Ask questions in natural language:**
    -   Once you have created tables, you can ask questions about them.
    -   "how many employees are in the engineering department?"
    -   "show me the name and salary of the marketing employees"
    -   "what is the average salary?"
