from flask import Flask, render_template, request, send_file
import pandas as pd
import sqlite3
from openai import OpenAI
from io import BytesIO

app = Flask(__name__)
client = OpenAI()
global user_data

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/')
def index():
    return render_template('index.html', data_exists=False, result_exists=False)

#Function when the upload and process button is pushed
@app.route('/upload', methods=['POST'])
def upload():
    global user_data
    if 'file' not in request.files:
        return 'No file part'
    file = request.files['file']
    if file.filename == '':
        return 'No selected file'
    if file:
        # create a pandas dataframe from the csv file
        user_data = pd.read_csv(file, index_col=False)
        #return to the html page with this data
        return render_template('index.html', data_exists=True, result_exists=False, num_rows = user_data.shape[0], data=user_data.head(5))


#Function when user presses 'execute query' button
@app.route('/query', methods=['POST'])
def run_query():
    global user_data
    user_query = request.form['user_query']
    
    # Build context
    columns = user_data.columns.tolist()
    sample_data = user_data.iloc[:5, :]
    context = f"The table has columns: {', '.join(columns)}. "
    context += f"For example, the first five rows are: {sample_data}. "

    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            { "role": "system", "content": f'''Your task is to translate a query written in plain english by a user into a valid, properly formatted sql query on an sql table hosted on sqlite3.
            The accuracy of your query is of the upmost importance. {context} Your output should contain only the sql query. If your entire output was ran against an sql table it should
            be valid. There should be no other text or comments in your sql query output. Do not include newline symbols. the table is called 'csv_data'. The names of the columns in this 
            sql table are exactly what i specified earlier. Keep any spaces or any other characters that were in the column names when you are writing the sql query. The column names 
            specified earlier are the exact column names in the sql table. Make sure to include ';' at the end of the sql query. Your response should only include one sql query, 
            respondong with multiple queries will cause the program to fail.'''},
    
            {"role": "assistant", "content": "translate this description of a query into a valid query for the sql table described to you: " + user_query},
        ]
    )
    
    sql_query = response.choices[0].message.content
    update_query = False
   
    # Try to create a sqlite database from the dataframe and execute_user_query
    try:
        connection = sqlite3.connect(":memory:")
        user_data.to_sql("csv_data", connection, index=False, if_exists='replace') #creates sql table in memory
        result, column_names = execute_user_query(sql_query, connection)
        
        #if the query was one that modified the table, update the dataframe
        if not sql_query.lower().startswith("select"):
            column_names = []
            result = []
            temp_query = "SELECT * FROM csv_data;"
            user_data = pd.read_sql_query(temp_query, connection)
            update_query = True
            
        connection.close()
    except Exception as e:
        connection.close()
        print(e)
        print(sql_query)
        result = []
        column_names = []
        sql_query += " \nERROR WHILE EXECUTING THIS. PLEASE TRY AGAIN."
    
    return render_template('index.html', data_exists=True, result_exists=True, num_rows=user_data.shape[0], data=user_data.head(5), result=result, column_names=column_names, query=sql_query, update_query=update_query)


# Executes query on the sql table, return the result and the column names
def execute_user_query(sql_query, connection):
    cursor = connection.cursor()
    cursor.execute(sql_query)
    result = cursor.fetchall()
    connection.commit()
    try:
        columns = [description[0] for description in cursor.description]
    except Exception as e:
        columns = []
        
    return result, columns


# Function to download csv file
@app.route('/download_file', methods=['GET'])
def download_file():
    csv_buffer = BytesIO()

    # Write the DataFrame to the buffer as a CSV file
    user_data.to_csv(csv_buffer, index=False)

    # Set the buffer position to the beginning
    csv_buffer.seek(0)

    # Create a Flask response with the CSV file
    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name="download_file.csv"
    )
    
    
if __name__ == '__main__':
    app.run(debug=True)