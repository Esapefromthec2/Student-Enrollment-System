from pathlib import Path
import sqlite3

from flask import Flask, abort, redirect, render_template, request, url_for

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "work.db"
SQL_FILE = BASE_DIR / "work.sql"


def initialize_database():
    if not DATABASE.exists():
        if not SQL_FILE.is_file():
            raise FileNotFoundError(f"Could not find {SQL_FILE}")

        with sqlite3.connect(DATABASE) as connection:
            connection.executescript(SQL_FILE.read_text(encoding="utf-8"))


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def get_tables():
    with sqlite3.connect(DATABASE) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()

    return [row[0] for row in rows]


def get_table_info(table_name):
    with sqlite3.connect(DATABASE) as connection:
        rows = connection.execute(
            f"PRAGMA table_info({quote_identifier(table_name)})"
        ).fetchall()

    primary_key_count = sum(1 for row in rows if row[5])

    fields = []
    for row in rows:
        name, data_type, not_null, default, primary_key = (
            row[1], row[2] or "", bool(row[3]), row[4], row[5]
        )

        # Let SQLite fill in a single INTEGER PRIMARY KEY automatically.
        auto_id = (
            primary_key_count == 1
            and primary_key == 1
            and data_type.strip().upper() == "INTEGER"
        )

        if auto_id:
            continue

        input_type = "text"
        if "INT" in data_type.upper():
            input_type = "number"
        elif any(t in data_type.upper() for t in ("REAL", "FLOA", "DOUB")):
            input_type = "number"

        fields.append({
            "name": name,
            "input_type": input_type,
            "required": default is None and (not_null or primary_key > 0),
        })

    return rows, fields


@app.route("/")
def index():
    return render_template("index.html", tables=get_tables())


@app.route("/table/<table_name>", methods=["GET", "POST"])
def show_table(table_name):
    if table_name not in get_tables():
        abort(404)

    table_info, fields = get_table_info(table_name)
    error = None
    form_values = request.form

    if request.method == "POST":
        values = {}
        missing = []

        for field in fields:
            value = request.form.get(field["name"], "").strip()

            if not value:
                if field["required"]:
                    missing.append(field["name"])
                continue

            values[field["name"]] = value

        if missing:
            error = "Fill in the required fields: " + ", ".join(missing)
        else:
            try:
                with sqlite3.connect(DATABASE) as connection:
                    if values:
                        names = ", ".join(
                            quote_identifier(name) for name in values
                        )
                        placeholders = ", ".join("?" for _ in values)
                        connection.execute(
                            f"INSERT INTO {quote_identifier(table_name)} "
                            f"({names}) VALUES ({placeholders})",
                            list(values.values()),
                        )
                    else:
                        connection.execute(
                            f"INSERT INTO {quote_identifier(table_name)} "
                            "DEFAULT VALUES"
                        )

                return redirect(url_for("show_table", table_name=table_name, added=1))

            except sqlite3.IntegrityError as exc:
                error = f"Could not add record: {exc}"

    with sqlite3.connect(DATABASE) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            f"SELECT * FROM {quote_identifier(table_name)}"
        )
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()

    return render_template(
        "table.html",
        table_name=table_name,
        fields=fields,
        columns=columns,
        rows=rows,
        error=error,
        form_values=form_values,
        added=request.args.get("added") == "1",
    )


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)