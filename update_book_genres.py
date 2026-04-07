import pandas as pd

from database import connect


def main():
    books = pd.read_csv("books_6users.csv")

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT CAST(book_id AS CHAR) FROM books")
    db_book_ids = {str(row[0]) for row in cursor.fetchall()}

    matched_in_db = 0
    changed = 0
    missing_in_db = 0

    for _, row in books.iterrows():
        if pd.isna(row.get("book_id")):
            continue

        book_id = str(int(row["book_id"]))
        genres = None if pd.isna(row.get("genres")) else str(row.get("genres"))

        if book_id not in db_book_ids:
            missing_in_db += 1
            continue

        matched_in_db += 1
        cursor.execute(
            """
            UPDATE books
            SET genres = %s
            WHERE CAST(book_id AS CHAR) = %s
            """,
            (genres, book_id),
        )

        if cursor.rowcount > 0:
            changed += 1

    conn.commit()
    conn.close()

    print(f"CSV books matched in DB: {matched_in_db}")
    print(f"Rows changed in DB: {changed}")
    print(f"Books from CSV not found in DB: {missing_in_db}")


if __name__ == "__main__":
    main()
