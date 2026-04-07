from __future__ import annotations

import argparse
from datetime import datetime

from database import connect


def _count_summary(cursor):
    cursor.execute("SELECT COUNT(*) FROM books")
    total_books = int(cursor.fetchone()[0])

    cursor.execute(
        """
        SELECT COUNT(DISTINCT CAST(s.book_id AS CHAR))
        FROM bookshelf s
        """
    )
    distinct_shelf_books = int(cursor.fetchone()[0])

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM books b
        WHERE NOT EXISTS (
            SELECT 1
            FROM bookshelf s
            WHERE CAST(s.book_id AS CHAR) = CAST(b.book_id AS CHAR)
        )
        """
    )
    unreferenced_books = int(cursor.fetchone()[0])

    return {
        "total_books": total_books,
        "distinct_shelf_books": distinct_shelf_books,
        "unreferenced_books": unreferenced_books,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Remove books not referenced by any bookshelf row. "
            "Use --dry-run to preview and --apply to execute."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    mode.add_argument("--apply", action="store_true", help="Backup and delete unreferenced rows")
    args = parser.parse_args()

    dry_run = not args.apply

    conn = connect()
    cursor = conn.cursor()

    try:
        before = _count_summary(cursor)
        print("Before cleanup:")
        print(f"  books.total_rows = {before['total_books']}")
        print(f"  bookshelf.distinct_book_ids = {before['distinct_shelf_books']}")
        print(f"  books.unreferenced_rows = {before['unreferenced_books']}")

        if before["unreferenced_books"] == 0:
            print("Nothing to clean. All books are referenced by at least one shelf row.")
            return

        if dry_run:
            print("Dry run only. Re-run with --apply to back up and delete these rows.")
            return

        backup_table = f"books_backup_unreferenced_{datetime.now():%Y%m%d_%H%M%S}"

        cursor.execute(f"CREATE TABLE {backup_table} LIKE books")
        cursor.execute(
            f"""
            INSERT INTO {backup_table}
            SELECT b.*
            FROM books b
            WHERE NOT EXISTS (
                SELECT 1
                FROM bookshelf s
                WHERE CAST(s.book_id AS CHAR) = CAST(b.book_id AS CHAR)
            )
            """
        )
        backed_up = cursor.rowcount

        cursor.execute(
            """
            DELETE b
            FROM books b
            WHERE NOT EXISTS (
                SELECT 1
                FROM bookshelf s
                WHERE CAST(s.book_id AS CHAR) = CAST(b.book_id AS CHAR)
            )
            """
        )
        deleted = cursor.rowcount
        conn.commit()

        after = _count_summary(cursor)

        print("Cleanup applied:")
        print(f"  backup_table = {backup_table}")
        print(f"  rows_backed_up = {int(backed_up)}")
        print(f"  rows_deleted = {int(deleted)}")
        print("After cleanup:")
        print(f"  books.total_rows = {after['total_books']}")
        print(f"  bookshelf.distinct_book_ids = {after['distinct_shelf_books']}")
        print(f"  books.unreferenced_rows = {after['unreferenced_books']}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
