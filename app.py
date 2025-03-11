from flask import Flask, render_template, request
import os
import pandas as pd
import ast  # Importing ast to convert string representation of lists into actual lists

app = Flask(__name__)

DATA_FOLDER = "data"

# Function to find the correct CSV file by username
def find_file_by_username(username):
    for file in os.listdir(DATA_FOLDER):
        if file.endswith(".csv"):
            file_path = os.path.join(DATA_FOLDER, file)
            try:
                df = pd.read_csv(file_path)
                if "Username" in df.columns and df["Username"][0].strip().lower() == username.strip().lower():
                    return file_path  # Found matching username
            except Exception as e:
                print(f"Error reading {file}: {e}")
    return None  # No match found

@app.route("/", methods=["GET", "POST"])
def index():
    user_data = None
    error = None

    if request.method == "POST":
        user_input = request.form.get("user_id").strip()

        if user_input.isdigit():  # If input is a numeric User ID
            file_path = os.path.join(DATA_FOLDER, f"{user_input}.csv")
        else:  # If input is a Username
            file_path = find_file_by_username(user_input)

        if file_path and os.path.exists(file_path):
            user_data = pd.read_csv(file_path).to_dict(orient="records")[0]

            # ? Convert stringified lists back into actual Python lists/dictionaries
            for key in ["Edits Per Weekday", "Edits Per Hour"]:
                if key in user_data and isinstance(user_data[key], str):
                    try:
                        user_data[key] = ast.literal_eval(user_data[key])  # Convert string to list/dict
                    except (SyntaxError, ValueError):
                        user_data[key] = {}  # Default to an empty dictionary if parsing fails

        else:
            error = "User not found or has no data."

    return render_template("index.html", user_data=user_data, error=error)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8001)
