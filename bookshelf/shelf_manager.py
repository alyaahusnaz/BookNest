from database import connect


def add_book(user_id, book_id, rating):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO bookshelf(user_id,book_id,rating,status) VALUES (%s,%s,%s,%s)",
        (user_id, book_id, rating, "reading")
    )

    conn.commit()
    conn.close()


def get_user_books(user_id):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT book_id FROM bookshelf WHERE user_id=%s",
        (user_id,)
    )

    books = cursor.fetchall()

    conn.close()

    return books

