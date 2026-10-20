
from flask import Flask, render_template

from database import initialize_database

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("base.html")


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
