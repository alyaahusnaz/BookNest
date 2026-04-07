import pandas as pd
import mysql.connector

# connect to mysql
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="KembarUmmi5544",
    database="booknest"
)

cursor = conn.cursor()

# load books dataset
books = pd.read_csv("books_6users.csv")

for _, row in books.iterrows():

    query = """
    INSERT INTO books (book_id, title, authors, description, genres)
    VALUES (%s, %s, %s, %s, %s)
    """

    # sanitize missing values so MySQL gets NULL instead of literal NaN
    book_id = int(row["book_id"]) if pd.notna(row["book_id"]) else None
    title = None if pd.isna(row["title"]) else row["title"]
    authors = None if pd.isna(row.get("author")) else row.get("author")
    description = None if pd.isna(row.get("description")) else row.get("description")
    genres = None if pd.isna(row.get("genres")) else row.get("genres")

    values = (book_id, title, authors, description, genres)

    cursor.execute(query, values)

conn.commit()

ratings = pd.read_csv("ratings_6users.csv")

for _, row in ratings.iterrows():

    query = """
    INSERT INTO ratings (user_id, book_id, rating)
    VALUES (%s, %s, %s)
    """

    # sanitize missing values
    user_id = int(row["user_id"]) if pd.notna(row["user_id"]) else None
    book_id = int(row["book_id"]) if pd.notna(row["book_id"]) else None
    rating = int(row["rating"]) if pd.notna(row["rating"]) else None

    values = (user_id, book_id, rating)

    cursor.execute(query, values)

conn.commit()
conn.close()

print("CSV data imported successfully")