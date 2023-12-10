from flask import Flask, render_template, request, redirect, url_for, send_file
import pandas as pd
import sqlite3
from openai import OpenAI
import csv
import io

app = Flask(__name__)
client = OpenAI()


user_query = ""
error_message = "Awaiting query"

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/')
def index():
    return render_template('index.html')

# Function to create a table in SQLite based on a DataFrame
def create_table_from_df(df, table_name='csv_data'):
    conn = sqlite3.connect('database.db')
    df.to_sql(table_name, conn, index=False, if_exists='replace')
    conn.close()

# Function to translate database into csv file for download to user
def db_to_csv(db_file, csv_file, table_name):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Execute a query to select all data from the specified table
    cursor.execute(f"SELECT * FROM {table_name};")
    data = cursor.fetchall()

    # Get the column names from the table
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = [column[1] for column in cursor.fetchall()]

    # Write data to the CSV file
    with open(csv_file, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)

        # Write the header row
        csv_writer.writerow(columns)

        # Write the data rows
        csv_writer.writerows(data)

    # Close the connection
    conn.close()

# Function to get the total number of rows from an SQLite table
def get_row_count(table_name='csv_data'):
    conn = sqlite3.connect('database.db')
    query = f"SELECT COUNT(*) FROM {table_name}"
    result = conn.execute(query).fetchone()[0]
    conn.close()
    return result

# Function to get the first 5 rows from an SQLite table
def get_first_5_rows(table_name='csv_data'):
    conn = sqlite3.connect('database.db')
    query = f"SELECT * FROM {table_name} LIMIT 5"
    result = conn.execute(query).fetchall()
    conn.close()
    return result

# Function to get the column names from an SQLite table
def get_column_names(table_name='csv_data'):
    conn = sqlite3.connect('database.db')
    query = f"PRAGMA table_info({table_name})"
    result = conn.execute(query).fetchall()
    conn.close()
    return [column[1] for column in result]

#Function to download csv file
@app.route('/download_file', methods=['GET'])
def download_file():
    # Set up response headers to trigger file download
    response = send_file(
        'download_file.csv',  # Path to the existing CSV file
        as_attachment=True,
        download_name='download_file.csv',
        mimetype='text/csv'
    )

    return response

#Function to upload csv file
@app.route('/upload', methods=['POST'])
def upload():
    global user_query  # Make the variable global to modify its value

    if 'file' not in request.files:
        return 'No file part'

    file = request.files['file']

    if file.filename == '':
        return 'No selected file'

    if file:
        # Save the uploaded CSV file
        file.save('uploaded_file.csv')

        # Process the CSV file
        df = pd.read_csv('uploaded_file.csv')

        # Create a table in SQLite based on the DataFrame
        create_table_from_df(df)

        # Get the total number of rows from the SQLite table
        row_count = get_row_count()

        # Get the first 5 rows from the SQLite table
        rows = get_first_5_rows()

        # Get the column names from the SQLite table
        columns = get_column_names()

        return render_template('index.html', row_count=row_count, rows=rows, columns=columns, err_msg=error_message)
    
# Function to execute openAI's SQL query
def execute_user_query(sql_query):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        # Execute the SQL query
        cursor.execute(sql_query)
        print(sql_query)
        # Fetch the result if it's a SELECT query
        result = cursor.fetchall() if sql_query.upper().startswith('SELECT') else None
        
        #print(type(result))
        # Commit the changes (in case of INSERT, UPDATE, DELETE queries)
        conn.commit()

        return result
    except Exception as e:
        # Handle errors
        #print(f"Error executing query: {e}")
        error_message = "Error processing your query, this was most likely a case of the openAI API making incorrect calls to the created SQL database. Please try again."
        return ["Error processing your query, this was most likely a case of the openAI API making incorrect calls to the created SQL database. Please try again."]
    finally:
        # Close the connection
        conn.close()

# Function to get column names from the cursor description
def get_column_names_from_query(sql_query):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute(sql_query)

    # Get column names from the cursor description
    column_names = [description[0] for description in cursor.description]

    # Close the connection
    conn.close()

    return column_names

#Function to accept and process user query
@app.route('/query', methods=['POST'])
def run_query():
    global user_query  # Make the variable global to modify its value
    user_query = request.form['user_query']

    # Build context
    columns = get_column_names()
    sample_data = get_first_5_rows()
    context = f"The table has columns: {', '.join(columns)}. "
    context += f"For example, the first five rows are: {sample_data}. "

    # Call OpenAI API
    response = client.chat.completions.create(
  model="gpt-3.5-turbo",
  messages=[
    {"role": "system", "content": "Your task is to translate a query written in plain english by a user into a valid, properly formatted sql query on an sql table hosted on sqlite3. The accuracy of your query is of the upmost importance." + context + "Your output should contain only the sql query. If your entire output was ran against an sql table it should be valid. There should be no other text or comments in your sql query output. Do not include newline symbols. the table is called 'csv_data'. The names of the columns in this sql table are exactly what i specified earlier. Keep any spaces or any other characters that were in the column names when you are writing the sql query. Do not add any extra characters such as '_' to try and format the column names correctly. The column names specified earlier are the exact column names in the sql table. Do not deviate from these column names even slightly. Make sure to include ';' after each sql statement. Your response should only include one sql query, respondong with multiple queries will cause the program to fail."},
    {"role": "assistant", "content": "translate this description of a query into a valid query for the sql table described to you: " + user_query},
  ]
)
    sql_query = response.choices[0].message.content
    #print(sql_query)

    # Execute the SQL query on your SQLite database
    try:

        result = execute_user_query(sql_query)
        if result == None:
            error_message = "Table was updated"
            column_names = []
            db_to_csv('database.db','download_file.csv','csv_data')
        else:
            column_names = get_column_names_from_query(sql_query)
            error_message = "SQL query was ran error free"
        print(error_message)
    except Exception as e:
        print(e)
        result = None
        column_names = []
        error_message = "Error processing your query, this was most likely a case of the openAI API making incorrect calls to the created SQL database. Please try again"
    # Render the template with the updated data
    row_count = get_row_count()
    rows = get_first_5_rows()
    columns = get_column_names()
    file_name = "uploaded_file.csv"

    return render_template('index.html', row_count=row_count, rows=rows, columns=columns, file_name=file_name, sql_query_result=result, column_names=column_names, err_msg=error_message)

if __name__ == '__main__':
    app.run(debug=True)