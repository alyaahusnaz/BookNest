from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database import connect, get_user_profile
from profile import ClickableAvatarLabel, apply_user_avatar
from window_state import show_with_parent_window_state


class AdminWindow(QWidget):
    def __init__(self, user_id):
        super().__init__()

        self.user_id = user_id
        self.user_profile = get_user_profile(user_id) or {}

        self.setWindowTitle("BookNest Admin")
        self.resize(1120, 760)
        self.setStyleSheet(self._build_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 14, 22, 22)
        root.setSpacing(14)

        root.addLayout(self._build_top_bar())
        root.addWidget(self._build_hero_card())
        root.addWidget(self._build_users_table())

        self.refresh_admin_data()

    def _build_top_bar(self):
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        brand = QLabel("BookNest Admin")
        brand.setObjectName("brandTitle")
        top_bar.addWidget(brand)

        top_bar.addStretch()

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setObjectName("navBtn")
        self.logout_btn.clicked.connect(self.logout)
        top_bar.addWidget(self.logout_btn)

        self.avatar = ClickableAvatarLabel()
        self.avatar.setObjectName("avatar")
        self.avatar.clicked.connect(self.show_profile)
        apply_user_avatar(self.avatar, self.user_profile, self.user_id, size=36)
        top_bar.addWidget(self.avatar)

        return top_bar

    def _build_hero_card(self):
        card = QFrame()
        card.setObjectName("heroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Admin Dashboard")
        title.setObjectName("sectionTitle")
        subtitle = QLabel("Manage users and review platform statistics.")
        subtitle.setObjectName("subtleText")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(12)
        self.stats_grid.setVerticalSpacing(12)

        self.stat_users = self._build_stat_card("Total Users", "0")
        self.stat_books = self._build_stat_card("Books Catalog", "0")
        self.stat_listings = self._build_stat_card("Marketplace Listings", "0")

        self.stats_grid.addWidget(self.stat_users, 0, 0)
        self.stats_grid.addWidget(self.stat_books, 0, 1)
        self.stats_grid.addWidget(self.stat_listings, 0, 2)
        layout.addLayout(self.stats_grid)

        return card

    def _build_stat_card(self, label_text, value_text):
        card = QFrame()
        card.setObjectName("statCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        label = QLabel(label_text)
        label.setObjectName("statLabel")
        layout.addWidget(label)

        value = QLabel(value_text)
        value.setObjectName("statValue")
        layout.addWidget(value)
        card.stat_value_label = value
        return card

    def _build_users_table(self):
        wrapper = QFrame()
        wrapper.setObjectName("tableCard")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)

        header = QLabel("Registered Users")
        header.setObjectName("sectionTitle")
        header.setStyleSheet("font-size: 16px; font-weight: 700; color: #11162a; background: #ffffff; padding-top: 8px; padding-bottom: 8px;")
        layout.addWidget(header)

        self.users_table = QTableWidget(0, 6)
        self.users_table.setHorizontalHeaderLabels(["ID", "Username", "Role", "Genre", "Author", "Action"])
        self.users_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.users_table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.users_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.users_table.setColumnWidth(5, 220)
        self.users_table.verticalHeader().setVisible(False)
        self.users_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.users_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.users_table, 0, Qt.AlignTop)
        layout.addStretch(1)

        return wrapper

    def view_user_details(self, user_id, username=""):
        conn = connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                COALESCE(role, 'user'),
                COALESCE(favorite_genre, ''),
                COALESCE(favorite_author, '')
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        user_row = cursor.fetchone()
        if not user_row:
            conn.close()
            QMessageBox.information(self, "User Details", "User not found.")
            return

        role, favorite_genre, favorite_author = user_row

        cursor.execute("SELECT COUNT(*) FROM bookshelf WHERE user_id = %s", (user_id,))
        total_books = int(cursor.fetchone()[0])

        cursor.execute(
            "SELECT COUNT(*) FROM bookshelf WHERE user_id = %s AND COALESCE(status, 'reading') = 'reading'",
            (user_id,),
        )
        reading_books = int(cursor.fetchone()[0])

        cursor.execute(
            "SELECT COUNT(*) FROM bookshelf WHERE user_id = %s AND COALESCE(status, '') = 'completed'",
            (user_id,),
        )
        completed_books = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM marketplace WHERE seller_id = %s", (user_id,))
        listings_count = int(cursor.fetchone()[0])

        conn.close()

        label = username or f"User {user_id}"
        details = (
            f"Username: {label}\n"
            f"Role: {role or 'user'}\n"
            f"Favorite Genre: {favorite_genre or '-'}\n"
            f"Favorite Author: {favorite_author or '-'}\n\n"
            f"Total Books on Shelf: {total_books}\n"
            f"Currently Reading: {reading_books}\n"
            f"Completed: {completed_books}\n"
            f"Marketplace Listings: {listings_count}"
        )
        QMessageBox.information(self, "User Details", details)

    def delete_user(self, user_id, username=""):
        if user_id == self.user_id:
            QMessageBox.warning(self, "Not Allowed", "You cannot delete the admin account currently in use.")
            return

        label = f"'{username}'" if username else "the selected user"
        confirm = QMessageBox.question(
            self,
            "Delete User",
            f"Delete {label} and all their shelf entries?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        conn = connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bookshelf WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM marketplace WHERE seller_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        conn.close()

        self.refresh_admin_data()
        QMessageBox.information(self, "Deleted", "User removed from the system.")

    def refresh_admin_data(self):
        conn = connect()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM books")
        books_count = int(cursor.fetchone()[0])

        cursor.execute("SELECT COUNT(*) FROM marketplace")
        listings_count = int(cursor.fetchone()[0])

        cursor.execute(
            "SELECT id, username, COALESCE(role, 'user'), COALESCE(favorite_genre, ''), COALESCE(favorite_author, '') FROM users ORDER BY id ASC"
        )
        rows = cursor.fetchall()
        conn.close()

        self.stat_users.stat_value_label.setText(str(users_count))
        self.stat_books.stat_value_label.setText(str(books_count))
        self.stat_listings.stat_value_label.setText(str(listings_count))

        self.users_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                item = QTableWidgetItem(str(value if value is not None else ""))
                if col_index == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.users_table.setItem(row_index, col_index, item)

            user_id = int(row[0])
            username = str(row[1] or "")
            view_btn = QPushButton("View")
            view_btn.setObjectName("infoBtn")
            view_btn.setFixedSize(54, 26)
            view_btn.clicked.connect(
                lambda _checked=False, uid=user_id, uname=username: self.view_user_details(uid, uname)
            )

            delete_btn = QPushButton("Delete")
            delete_btn.setObjectName("dangerBtn")
            delete_btn.setFixedSize(64, 26)
            delete_btn.clicked.connect(lambda _checked=False, uid=user_id, uname=username: self.delete_user(uid, uname))
            if user_id == self.user_id:
                delete_btn.setEnabled(False)
                delete_btn.setText("Admin")

            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 0, 4, 0)
            cell_layout.setSpacing(6)
            cell_layout.addStretch()
            cell_layout.addWidget(view_btn)
            cell_layout.addWidget(delete_btn)
            cell_layout.addStretch()
            self.users_table.setCellWidget(row_index, 5, cell)

        self.users_table.resizeColumnsToContents()
        self.users_table.resizeRowsToContents()

        table_height = self.users_table.horizontalHeader().height() + 16
        for row_index in range(self.users_table.rowCount()):
            table_height += self.users_table.rowHeight(row_index)

        table_height = max(160, min(table_height + 8, 320))
        self.users_table.setFixedHeight(table_height)

    def show_profile(self):
        from profile import ProfileDialog

        dialog = ProfileDialog(self.user_id, self)
        if dialog.exec() != ProfileDialog.Accepted or not dialog.saved_profile:
            return

        self.user_profile = dialog.saved_profile
        apply_user_avatar(self.avatar, self.user_profile, self.user_id, size=36)

    def logout(self):
        from auth.login import LoginWindow

        self.login = LoginWindow()
        show_with_parent_window_state(self, self.login)
        self.close()

    def _build_stylesheet(self):
        return """
            QWidget {
                background: #f4f6fb;
                color: #171b27;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QLabel#brandTitle {
                font-size: 28px;
                font-weight: 700;
                color: #151a2d;
            }
            QPushButton#navBtn {
                border: none;
                background: transparent;
                padding: 6px 10px;
                font-size: 14px;
                color: #4b5474;
            }
            QPushButton#dangerBtn {
                border: none;
                background: #ffe5e5;
                color: #a42727;
                border-radius: 8px;
                padding: 0px;
                font-weight: 600;
            }
            QPushButton#dangerBtn:hover {
                background: #ffd4d4;
            }
            QPushButton#infoBtn {
                border: none;
                background: #e8f0ff;
                color: #244a96;
                border-radius: 8px;
                padding: 0px;
                font-weight: 600;
            }
            QPushButton#infoBtn:hover {
                background: #d8e7ff;
            }
            QLabel#avatar {
                background: #dbe4ff;
                color: #1f3ba2;
                border-radius: 18px;
                font-weight: 700;
            }
            QFrame#heroCard,
            QFrame#tableCard {
                background: #ffffff;
                border: 1px solid #e3e8f3;
                border-radius: 14px;
            }
            QLabel#sectionTitle {
                font-size: 20px;
                font-weight: 700;
                color: #11162a;
            }
            QLabel#subtleText {
                color: #70799b;
                font-size: 12px;
            }
            QFrame#statCard {
                background: #f7f9ff;
                border: 1px solid #dee5f3;
                border-radius: 12px;
            }
            QLabel#statLabel {
                color: #5f6788;
                font-size: 11px;
            }
            QLabel#statValue {
                color: #131a30;
                font-size: 26px;
                font-weight: 700;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d9deeb;
                border-radius: 10px;
                gridline-color: #e7ebf3;
            }
            QHeaderView::section {
                background: #eef2fb;
                color: #24304f;
                padding: 8px;
                border: none;
                font-weight: 600;
            }
        """
