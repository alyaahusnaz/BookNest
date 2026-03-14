import csv
import mysql.connector
from pathlib import Path

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "KembarUmmi5544",
    "database": "booknest",
}


def connect():
    return mysql.connector.connect(**DB_CONFIG)


def _get_table_columns(cursor, table_name):
    cursor.execute("SHOW COLUMNS FROM " + table_name)
    return {row[0] for row in cursor.fetchall()}


def _get_column_type(cursor, table_name, column_name):
    cursor.execute("SHOW COLUMNS FROM " + table_name + " LIKE %s", (column_name,))
    row = cursor.fetchone()
    if not row:
        return ""
    return str(row[1]).lower()


def create_tables():

    conn = connect()
    cursor = conn.cursor()

    # users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(255) UNIQUE,
        password VARCHAR(255),
        favorite_genre VARCHAR(255),
        favorite_author VARCHAR(255)
    )
    """)

    # bookshelf table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookshelf(
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        book_id VARCHAR(255),
        rating INT,
        status VARCHAR(50)
    )
    """)

    # marketplace table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS marketplace(
        id INT AUTO_INCREMENT PRIMARY KEY,
        seller_id INT,
        book_id VARCHAR(255),
        price DOUBLE,
        location VARCHAR(255)
    )
    """)

    # books catalog table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS books(
        book_id VARCHAR(255) PRIMARY KEY,
        title TEXT,
        authors TEXT,
        description TEXT,
        genres TEXT
    )
    """)

    _ensure_users_columns(cursor)
    _ensure_books_columns(cursor)
    _ensure_key_column_types(cursor)

    conn.commit()
    conn.close()

    ensure_books_catalog()


def _ensure_users_columns(cursor):
    existing_cols = _get_table_columns(cursor, "users")
    if "favorite_genre" not in existing_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN favorite_genre TEXT")
    if "favorite_author" not in existing_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN favorite_author TEXT")


def _ensure_books_columns(cursor):
    existing_cols = _get_table_columns(cursor, "books")
    if "genres" not in existing_cols:
        cursor.execute("ALTER TABLE books ADD COLUMN genres TEXT")
    if "cover_img" not in existing_cols:
        cursor.execute("ALTER TABLE books ADD COLUMN cover_img TEXT")


def _ensure_key_column_types(cursor):
    # Older MySQL schemas were created with INT book_id, which breaks ISBN inserts.
    books_book_id_type = _get_column_type(cursor, "books", "book_id")
    if books_book_id_type.startswith("int"):
        cursor.execute("ALTER TABLE books MODIFY COLUMN book_id VARCHAR(255) NOT NULL")

    shelf_book_id_type = _get_column_type(cursor, "bookshelf", "book_id")
    if shelf_book_id_type and not shelf_book_id_type.startswith("varchar(255)"):
        cursor.execute("ALTER TABLE bookshelf MODIFY COLUMN book_id VARCHAR(255)")


def _find_books_csv():
    base_dir = Path(__file__).resolve().parent
    preferred = [base_dir / "books_6users.csv", base_dir / "books.csv"]

    for path in preferred:
        if path.exists():
            return path

    return None


def ensure_books_catalog():
    """Populate books table from CSV if it is empty."""

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM books")
    existing_count = cursor.fetchone()[0]

    csv_path = _find_books_csv()
    if not csv_path:
        conn.close()
        return

    rows_to_insert = []
    rows_to_enrich = []
    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            book_id = (row.get("book_id") or "").strip()
            title = (row.get("title") or "").strip()

            if not book_id or not title:
                continue

            authors = (row.get("authors") or row.get("author") or "").strip() or None
            description = (row.get("description") or "").strip() or None
            genres = (row.get("genres") or "").strip() or None
            cover_img = (row.get("coverImg") or row.get("cover_img") or "").strip() or None

            rows_to_enrich.append((authors, description, genres, cover_img, book_id))

            rows_to_insert.append((book_id, title, authors, description, genres, cover_img))

    if existing_count == 0 and rows_to_insert:
        cursor.executemany(
            "INSERT IGNORE INTO books (book_id, title, authors, description, genres, cover_img) VALUES (%s, %s, %s, %s, %s, %s)",
            rows_to_insert,
        )
        conn.commit()

    # Backfill metadata for older rows that were inserted before genres/preferences existed.
    if rows_to_enrich:
        cursor.executemany(
            """
            UPDATE books
            SET
                authors = COALESCE(NULLIF(authors, ''), %s),
                description = COALESCE(NULLIF(description, ''), %s),
                genres = COALESCE(NULLIF(genres, ''), %s),
                cover_img = COALESCE(NULLIF(cover_img, ''), %s)
            WHERE book_id = %s
            """,
            rows_to_enrich,
        )
        conn.commit()

    conn.close()


def seed_user_bookshelf_from_ratings(user_id):
    """Seed bookshelf rows for a user from the ratings table if they have no shelf rows."""

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM bookshelf WHERE user_id = %s", (user_id,))
    existing_count = cursor.fetchone()[0]
    if existing_count > 0:
        conn.close()
        return

    cursor.execute(
        "SELECT book_id, rating FROM ratings WHERE user_id = %s",
        (user_id,),
    )
    rating_rows = cursor.fetchall()

    rows_to_insert = []
    for book_id, rating in rating_rows:
        if book_id is None:
            continue
        try:
            rating = int(rating) if rating is not None else 0
        except (ValueError, TypeError):
            rating = 0
        status = "completed" if rating >= 4 else "reading"
        rows_to_insert.append((int(user_id), str(book_id), rating, status))

    if rows_to_insert:
        cursor.executemany(
            "INSERT INTO bookshelf(user_id, book_id, rating, status) VALUES (%s, %s, %s, %s)",
            rows_to_insert,
        )
        conn.commit()

    conn.close()