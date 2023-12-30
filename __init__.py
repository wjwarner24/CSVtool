from flask import Flask, render_template, request, session, Response
import pandas as pd
import sqlite3
from openai import OpenAI
from io import StringIO
import uuid
from sqlalchemy import create_engine
import csv
import os

app = Flask(__name__)
client = OpenAI()
print(os.getcwd())
database_path = 'sqlite:////var/www/webApp/webApp/data.db'
engine = create_engine(database_path)
@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/')
def index():
    return render_template('index.html', data_exists=False, result_exists=False)

#Function when the upload and process button is pushed
@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return 'No file part'
    file = request.files['file']
    if file.filename == '':
        return 'No selected file'
    if file:
        table_id = str(uuid.uuid4())
        table_id = f'a{table_id}'
        table_id = table_id.replace('-', '')

        session.pop('id', None)
        session.pop('name', None)
        session['id'] = table_id
        session['name'] = file.filename

        user_data = pd.read_csv(file)
        user_data.to_sql(table_id, con=engine, index=False)
        num_rows, columns, first_five_rows = get_display_data()

        return render_template('index.html', data_exists=True, result_exists=False, num_rows=num_rows, data=first_five_rows, display_columns=columns)


#Function when user presses 'execute query' button
@app.route('/query', methods=['POST'])
def run_query():
    
    user_query = request.form['user_query']
    
    row_count, column_names, first_five_rows = get_display_data()
    context = f"The table has {row_count} rows, and it has columns: {column_names}. For example, the first five rows are: {first_five_rows}"
    
    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            { "role": "system", "content": f'''Your task is to translate a query written in plain english by a user into a valid, properly formatted sql query on an sql table hosted on sqlite3.
            The accuracy of your query is of the upmost importance. {context} Your output should contain only the sql query. If your entire output was ran against an sql table it should
            be valid. There should be no other text or comments in your sql query output. Do not include newline symbols. the table is called '{session.get('id')}'. The names of the columns in this 
            sql table are exactly what i specified earlier. Keep any spaces or any other characters that were in the column names when you are writing the sql query. The column names 
            specified earlier are the exact column names in the sql table. Make sure to include ';' at the end of the sql query. Your response should only include one sql query, 
            respondong with multiple queries will cause the program to fail.'''},
    
            {"role": "assistant", "content": "translate this description of a query into a valid query for the sql table described to you: " + user_query},
        ]
    )
    
    sql_query = response.choices[0].message.content
    update_query = False
    query_column_names=""
   
    try:
        result, query_column_names = execute_user_query(sql_query)
        if not sql_query.lower().startswith("select"):
            column_names = []
            result = []
            update_query = True
            
        
    except Exception as e:
        print(e)
        print(sql_query)
        result = []
        column_names = []
        sql_query = "ERROR WHILE EXECUTING THIS. PLEASE TRY AGAIN. " + sql_query
    
    num_rows, column_names, first_five_rows = get_display_data()

    return render_template('index.html', data_exists=True, result_exists=True, num_rows=num_rows, data=first_five_rows, result=result, column_names=query_column_names, display_columns=column_names, query=sql_query, update_query=update_query)


# Executes query on the sql table, return the result and the column names
def execute_user_query(sql_query):
    conn = sqlite3.connect('/var/www/webApp/webApp/data.db')
    cursor = conn.cursor()
    cursor.execute(sql_query)
    result = cursor.fetchall()
    conn.commit()
    try:
        columns = [description[0] for description in cursor.description]
    except Exception as e:
        columns = []
    conn.close() 
    return result, columns


@app.route('/download_file', methods=['GET'])
def download_file():
    # Connect to the SQLite database
    conn = sqlite3.connect('/var/www/webApp/webApp/data.db')
    cursor = conn.cursor()
    table_id = session.get('id')
    query = f'SELECT * FROM {table_id}'
    # Execute a SELECT query to get all data from the table
    cursor.execute(query)
    rows = cursor.fetchall()

    # Prepare CSV data
    csv_data = StringIO()
    csv_writer = csv.writer(csv_data)
    
    # Write header
    header = [description[0] for description in cursor.description]
    csv_writer.writerow(header)

    # Write data
    csv_writer.writerows(rows)

    # Close the database connection
    conn.close()
    updated_name = session.get('name') + '_updated'
    # Prepare the response
    response = Response(
        csv_data.getvalue(),
        content_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename={updated_name}.csv'}
    )

    return response

# Get the data necessary to display a preview of the table: number of rows, column names, and the first five rows
def get_display_data():

    table_id = session.get('id')
    row_count_query = f"SELECT COUNT(*) FROM {table_id};"
    column_names_query = f'PRAGMA table_info({table_id});'
    first_five_rows_query = f'SELECT * FROM {table_id} LIMIT 5;'
    conn = sqlite3.connect('/var/www/webApp/webApp/data.db')
    cursor = conn.cursor()

    cursor.execute(row_count_query)
    row_count = cursor.fetchall()
    row_count = row_count[0][0]

    cursor.execute(column_names_query)
    column_names = cursor.fetchall()

    cursor.execute(first_five_rows_query)
    first_five_rows = cursor.fetchall()
    conn.close()

    columns = []
    for list in column_names:
        columns.append(list[1])

    return row_count, columns, first_five_rows


if __name__ == '__main__':
    app.run(debug=True)
