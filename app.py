
from flask import Flask, render_template, request

from database import initialize_database
from attendance_calculator import classes_needed, classes_missable

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("base.html")


@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    result = None
    error = None

    if request.method == "POST":
        try:
            attended = int(request.form["attended"])
            total = int(request.form["total"])
            upcoming = int(request.form["upcoming"])
            target_percent = float(request.form["target"])
        except (ValueError, KeyError):
            error = "Enter valid numbers for all fields."
        else:
            target = target_percent / 100
            try:
                if total == 0:
                    raise ValueError("Total classes must be greater than zero.")
                if attended < 0 or attended > total:
                    raise ValueError(
                        "Attended classes must be between 0 and total classes."
                    )
                if upcoming < 0:
                    raise ValueError("Upcoming classes cannot be negative.")
                if not 0 < target <= 1:
                    raise ValueError(
                        "Target must be greater than 0 and at most 100%."
                    )

                result = {
                    "current_percent": attended / total * 100,
                    "target_percent": target_percent,
                    "needed": classes_needed(attended, total, target),
                    "missable": classes_missable(attended, total, upcoming, target),
                    "attended": attended,
                    "total": total,
                    "upcoming": upcoming,
                }
            except ValueError as exc:
                error = str(exc)

    return render_template("attendance.html", result=result, error=error)


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
