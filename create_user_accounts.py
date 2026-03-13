"""Create login accounts for each user_id in the ratings dataset.

This script will:
- Read the unique user_id values from ratings_6users.csv
- Create a row in the SQLite users table for each user_id
- Use a predictable username and password per user for easy login

Usage:
    python create_user_accounts.py

After running, users can login via the GUI using the generated credentials.
"""

import pandas as pd

from database import connect


def create_accounts_from_ratings(ratings_csv_path: str):
    ratings = pd.read_csv(ratings_csv_path)
    user_ids = sorted(ratings["user_id"].dropna().unique().astype(int))

    conn = connect()
    cur = conn.cursor()

    created = []
    skipped = []

    for user_id in user_ids:
        username = f"user{user_id}"
        password = f"pass{user_id}"

        # Convert to Python int for SQLite compatibility
        user_id = int(user_id)

        # Use explicit id so it matches the rating user_id
        cur.execute(
            "INSERT IGNORE INTO users (id, username, password) VALUES (%s, %s, %s)",
            (user_id, username, password),
        )

        if cur.rowcount:
            created.append((user_id, username, password))
        else:
            skipped.append(user_id)

    conn.commit()
    conn.close()

    return created, skipped


if __name__ == "__main__":
    created, skipped = create_accounts_from_ratings("ratings_6users.csv")

    print(f"Created {len(created)} user(s)")
    for uid, username, password in created:
        print(f"  id={uid}  username={username}  password={password}")

    if skipped:
        print(f"Skipped {len(skipped)} existing user_id(s): {skipped}")

    print("Done. Use the generated username/password to login via auth/login.py")
