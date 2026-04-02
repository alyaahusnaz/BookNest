import csv
import json
import threading
import urllib.request
import urllib.parse
import zlib
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database import connect, get_user_profile, seed_user_bookshelf_from_ratings
from profile import ClickableAvatarLabel, ProfileDialog, apply_user_avatar
from recommender.recommender import hybrid_recommend
from window_state import show_with_parent_window_state


class CoverLabel(QLabel):
    """Async cover image: shows a dark placeholder then swaps in the real image."""

    class _Bridge(QObject):
        loaded = Signal(bytes)

    def __init__(self, url: str, height: int, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        self.setStyleSheet("background: #2a3250; border-radius: 8px 8px 0 0;")
        self._bridge = self._Bridge()
        self._bridge.loaded.connect(self._on_loaded)
        if url:
            threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url: str):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read()
            self._bridge.loaded.emit(data)
        except Exception:
            pass

    def _on_loaded(self, data: bytes):
        pixmap = QPixmap()
        if pixmap.loadFromData(data) and not pixmap.isNull():
            w = self.width() if self.width() > 0 else 200
            scaled = pixmap.scaled(w, self.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.setPixmap(scaled)


class BookDetailDialog(QDialog):
    """Book details dialog shown when a user clicks a book card."""

    @staticmethod
    def _status_to_display(status_value):
        return "Completed" if (status_value or "").strip().lower() == "completed" else "Currently Reading"

    @staticmethod
    def _display_to_status(display_value):
        return "completed" if (display_value or "").strip().lower() == "completed" else "reading"

    def __init__(self, book: dict, parent=None, remove_callback=None, edit_book_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Book Details")
        self.setMinimumSize(680, 420)
        self._remove_callback = remove_callback
        self._edit_book_callback = edit_book_callback
        self._book = dict(book)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        content = QHBoxLayout()
        content.setSpacing(16)

        cover = CoverLabel(book.get("cover_img", ""), 280)
        cover.setFixedWidth(210)
        cover.setStyleSheet("background: #2a3250; border-radius: 10px;")
        content.addWidget(cover)

        info_col = QVBoxLayout()
        info_col.setSpacing(8)

        self.title_lbl = QLabel(book.get("title") or "Unknown title")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet("font-size: 24px; font-weight: 700; color: #11162a;")
        info_col.addWidget(self.title_lbl)

        self.author_lbl = QLabel(f"Author: {book.get('authors') or 'Unknown author'}")
        self.author_lbl.setWordWrap(True)
        self.author_lbl.setStyleSheet("font-size: 13px; color: #4b5474;")
        info_col.addWidget(self.author_lbl)

        rating_value = float(book.get("rating") or 0)
        stars = "★" * max(0, min(5, int(round(rating_value))))
        self.rating_lbl = QLabel(f"Rating: {rating_value:.1f}  {stars}")
        self.rating_lbl.setStyleSheet("font-size: 13px; color: #1b2133; font-weight: 600;")
        info_col.addWidget(self.rating_lbl)

        self.status_lbl = QLabel(f"Status: {self._status_to_display(book.get('status'))}")
        self.status_lbl.setStyleSheet("font-size: 13px; color: #1b2133; font-weight: 600;")
        info_col.addWidget(self.status_lbl)

        description_title = QLabel("Description")
        description_title.setStyleSheet("font-size: 13px; color: #4b5474; font-weight: 700;")
        info_col.addWidget(description_title)

        self.description_lbl = QLabel(book.get("description") or "No description available.")
        self.description_lbl.setWordWrap(True)
        self.description_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.description_lbl.setStyleSheet("font-size: 12px; color: #3f4661;")
        info_col.addWidget(self.description_lbl, 1)

        content.addLayout(info_col, 1)
        root.addLayout(content, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        if self._edit_book_callback is not None:
            edit_btn = buttons.addButton("Edit Book Details", QDialogButtonBox.ActionRole)
            edit_btn.clicked.connect(self._handle_edit_book_clicked)
        if self._remove_callback is not None:
            remove_btn = buttons.addButton("Remove from Shelf", QDialogButtonBox.DestructiveRole)
            remove_btn.clicked.connect(self._handle_remove_clicked)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    def _handle_remove_clicked(self):
        if self._remove_callback is None:
            return
        removed = self._remove_callback()
        if removed:
            self.accept()

    def _handle_edit_book_clicked(self):
        if self._edit_book_callback is None:
            return

        edit_dialog = QDialog(self)
        edit_dialog.setWindowTitle("Edit Book Details")
        edit_dialog.setMinimumWidth(480)
        form = QFormLayout(edit_dialog)

        title_input = QLineEdit(self._book.get("title") or "")
        form.addRow("Title", title_input)

        author_input = QLineEdit(self._book.get("authors") or "")
        form.addRow("Author", author_input)

        cover_input = QLineEdit(self._book.get("cover_img") or "")
        form.addRow("Cover URL", cover_input)

        description_input = QTextEdit()
        description_input.setPlainText(self._book.get("description") or "")
        description_input.setMinimumHeight(120)
        form.addRow("Description", description_input)

        rating_input = QSpinBox()
        rating_input.setRange(1, 5)
        rating_input.setValue(max(1, min(5, int(round(float(self._book.get("rating") or 1))))))
        form.addRow("Rating", rating_input)

        status_input = QComboBox()
        status_input.addItems(["Currently Reading", "Completed"])
        status_input.setCurrentText(self._status_to_display(self._book.get("status")))
        form.addRow("Status", status_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(edit_dialog.accept)
        buttons.rejected.connect(edit_dialog.reject)
        form.addRow(buttons)

        if edit_dialog.exec() != QDialog.Accepted:
            return

        updated = {
            "title": title_input.text().strip(),
            "authors": author_input.text().strip(),
            "cover_img": cover_input.text().strip(),
            "description": description_input.toPlainText().strip(),
            "rating": int(rating_input.value()),
            "status": self._display_to_status(status_input.currentText()),
        }

        saved = self._edit_book_callback(updated)
        if saved:
            self._book.update(updated)
            self.title_lbl.setText(updated["title"] or "Unknown title")
            self.author_lbl.setText(f"Author: {updated['authors'] or 'Unknown author'}")
            stars = "★" * max(0, min(5, int(round(float(updated.get("rating") or 0)))))
            self.rating_lbl.setText(f"Rating: {float(updated.get('rating') or 0):.1f}  {stars}")
            self.status_lbl.setText(f"Status: {self._status_to_display(updated.get('status'))}")
            self.description_lbl.setText(updated["description"] or "No description available.")


class BookRecommendationApp(QWidget):

    def __init__(self, user_id):
        super().__init__()

        self.user_id = user_id
        self.user_profile = get_user_profile(user_id) or {}
        seed_user_bookshelf_from_ratings(self.user_id)
        self.books_index = self._load_books_index()
        self.cover_index = self._load_cover_index()
        self.book_metadata_index = self._load_book_metadata_index()
        self.title_to_book_id = {}
        for book_id, title in self.books_index.items():
            self.title_to_book_id.setdefault(title, book_id)

        self.setWindowTitle("BookNest Recommendations")
        self.resize(980, 700)
        self.setStyleSheet(self._build_stylesheet())

        root = QVBoxLayout()
        root.setContentsMargins(22, 14, 22, 22)
        root.setSpacing(14)

        root.addLayout(self._build_top_bar())
        root.addWidget(self._build_banner())
        root.addLayout(self._build_toolbar())
        root.addWidget(self._build_cards_section(), 1)

        self.setLayout(root)
        self.refresh_recommendations()

    def _build_top_bar(self):
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        brand = QLabel("BookNest")
        brand.setObjectName("brandTitle")
        top_bar.addWidget(brand)

        top_bar.addSpacing(12)

        self.bookshelf_nav_btn = QPushButton("Bookshelf")
        self.bookshelf_nav_btn.setObjectName("navBtn")
        self.bookshelf_nav_btn.clicked.connect(self.open_bookshelf)
        top_bar.addWidget(self.bookshelf_nav_btn)

        self.marketplace_nav_btn = QPushButton("Exchange & Marketplace")
        self.marketplace_nav_btn.setObjectName("navBtn")
        self.marketplace_nav_btn.clicked.connect(self.open_marketplace)
        top_bar.addWidget(self.marketplace_nav_btn)

        self.recommendations_nav_btn = QPushButton("Recommendations")
        self.recommendations_nav_btn.setObjectName("navBtnActive")
        top_bar.addWidget(self.recommendations_nav_btn)

        top_bar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search books...")
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self.refresh_recommendations)
        top_bar.addWidget(self.search_input)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setObjectName("navBtn")
        self.logout_btn.clicked.connect(self.logout)
        top_bar.addWidget(self.logout_btn)

        self.avatar = ClickableAvatarLabel()
        self.avatar.setObjectName("avatar")
        self.avatar.clicked.connect(self.open_profile_dialog)
        apply_user_avatar(self.avatar, self.user_profile, self.user_id, size=36)
        top_bar.addWidget(self.avatar)

        return top_bar

    def _build_banner(self):
        banner = QFrame()
        banner.setObjectName("recommendationBanner")

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(20, 16, 20, 16)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        title = QLabel("AI-Powered Book Recommendations")
        title.setObjectName("bannerTitle")
        text_col.addWidget(title)

        subtitle = QLabel(
            "Discover your next favorite book with hybrid recommendations "
            "that combine collaborative and content-based signals."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("bannerSubtitle")
        text_col.addWidget(subtitle)

        chips = QLabel("Hybrid AI Technology   |   NLP Processing   |   TF-IDF Analysis")
        chips.setObjectName("bannerChips")
        text_col.addWidget(chips)

        layout.addLayout(text_col, 3)

        icon = QLabel("AI")
        icon.setObjectName("bannerIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(86, 86)
        layout.addWidget(icon, 0, Qt.AlignRight | Qt.AlignVCenter)

        return banner

    def _build_toolbar(self):
        toolbar = QHBoxLayout()

        title = QLabel("Your Personalized Recommendations")
        title.setObjectName("sectionTitle")
        toolbar.addWidget(title)

        toolbar.addStretch()

        self.sort_box = QComboBox()
        self.sort_box.addItems(["Sort by Rating", "Sort by Match", "Sort by Title"])
        self.sort_box.currentTextChanged.connect(self.refresh_recommendations)
        toolbar.addWidget(self.sort_box)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("primaryBtn")
        refresh_btn.clicked.connect(self.refresh_recommendations)
        toolbar.addWidget(refresh_btn)

        return toolbar

    def _build_cards_section(self):
        wrapper = QFrame()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("No recommendations available for this user yet.")
        self.empty_label.setObjectName("subtleText")
        layout.addWidget(self.empty_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)

        self.scroll.setWidget(self.grid_host)
        layout.addWidget(self.scroll, 1)

        load_more = QPushButton("Load More Recommendations")
        load_more.setObjectName("mutedBtn")
        load_more.clicked.connect(self.refresh_recommendations)
        layout.addWidget(load_more, alignment=Qt.AlignHCenter)

        return wrapper

    def _load_cover_index(self):
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT book_id, cover_img FROM books WHERE cover_img IS NOT NULL AND cover_img != ''")
        rows = cursor.fetchall()
        conn.close()
        return {str(book_id): url for book_id, url in rows}

    def _load_books_index(self):
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT book_id, title FROM books WHERE title IS NOT NULL AND TRIM(title) != ''"
        )
        db_rows = cursor.fetchall()
        conn.close()

        if db_rows:
            return {str(book_id): title for book_id, title in db_rows}

        candidates = [
            Path(__file__).resolve().parent / "books_6users.csv",
            Path(__file__).resolve().parent / "books.csv",
        ]

        for path in candidates:
            if not path.exists():
                continue

            book_map = {}
            with path.open("r", encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    book_id = (row.get("book_id") or "").strip()
                    title = (row.get("title") or "").strip()
                    if book_id and title:
                        book_map[book_id] = title
            if book_map:
                return book_map

        return {}

    def _load_book_metadata_index(self):
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                book_id,
                COALESCE(authors, ''),
                COALESCE(description, '')
            FROM books
            """
        )
        rows = cursor.fetchall()
        conn.close()

        result = {}
        for book_id, authors, description in rows:
            result[str(book_id)] = {
                "authors": (authors or "").strip(),
                "description": (description or "").strip(),
            }
        return result

    def _mock_metadata(self, title):
        score = abs(hash(title))
        rating = 3.7 + (score % 13) / 10
        rating = min(rating, 5.0)
        votes = 3500 + (score % 19000)
        match = 85 + (score % 12)
        genres = ["Mystery", "Fiction", "Thriller", "Literary", "Science Fiction"]
        genre = genres[score % len(genres)]
        return {
            "rating": rating,
            "votes": votes,
            "match": match,
            "genre": genre,
        }

    def _get_recommendation_items(self):
        try:
            titles = hybrid_recommend(self.user_id, top_n=20)
        except Exception as exc:
            QMessageBox.warning(self, "Recommendation Error", str(exc))
            return []

        items = []
        for title in titles:
            meta = self._mock_metadata(title)
            book_id = self.title_to_book_id.get(title, "")
            book_meta = self.book_metadata_index.get(book_id, {})
            items.append(
                {
                    "title": title,
                    "book_id": book_id,
                    "rating": meta["rating"],
                    "votes": meta["votes"],
                    "match": meta["match"],
                    "genre": meta["genre"],
                    "cover_img": self.cover_index.get(book_id, ""),
                    "authors": book_meta.get("authors") or "Unknown author",
                    "description": book_meta.get("description") or "No description available.",
                }
            )

        return items

    def refresh_recommendations(self):
        items = self._get_recommendation_items()

        query = self.search_input.text().strip().lower()
        if query:
            items = [item for item in items if query in item["title"].lower()]

        sort_value = self.sort_box.currentText()
        if sort_value == "Sort by Match":
            items.sort(key=lambda x: x["match"], reverse=True)
        elif sort_value == "Sort by Title":
            items.sort(key=lambda x: x["title"].lower())
        else:
            items.sort(key=lambda x: x["rating"], reverse=True)

        self._render_cards(items)

    def _render_cards(self, items):
        while self.grid.count():
            child = self.grid.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

        self.empty_label.setVisible(not items)

        for idx, item in enumerate(items):
            row = idx // 4
            col = idx % 4
            self.grid.addWidget(self._build_book_card(item), row, col)

    def _build_book_card(self, item):
        card = QFrame()
        card.setObjectName("recCard")
        card.setFixedSize(220, 360)
        card.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(6)

        cover = CoverLabel(item.get("cover_img", ""), 130)
        cover.setObjectName("recCover")
        layout.addWidget(cover)

        meta_row = QHBoxLayout()
        genre_chip = QLabel(item["genre"])
        genre_chip.setObjectName("genreChip")
        match = QLabel(f"{item['match']}% Match")
        match.setObjectName("matchLabel")
        meta_row.addWidget(genre_chip)
        meta_row.addStretch()
        meta_row.addWidget(match)
        meta_row.setContentsMargins(10, 0, 10, 0)
        layout.addLayout(meta_row)

        title = QLabel(item["title"])
        title.setObjectName("recTitle")
        title.setWordWrap(True)
        title.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(title)

        author_name = item.get("authors") or "Unknown author"
        author_name = author_name.split(",")[0].strip() if author_name else "Unknown author"
        author = QLabel(f"by {author_name}")
        author.setObjectName("recAuthor")
        author.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(author)

        stars = "★" * max(1, min(5, int(round(float(item.get("rating") or 0)))))
        byline = QLabel(f"{stars}  {item['rating']:.1f} ({item['votes']:,})")
        byline.setObjectName("recRating")
        byline.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(byline)

        description = item.get("description") or "No description available."
        if len(description) > 108:
            description = description[:105].rstrip() + "..."
        description_lbl = QLabel(description)
        description_lbl.setWordWrap(True)
        description_lbl.setObjectName("recDescription")
        description_lbl.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(description_lbl)

        layout.addStretch()

        button = QPushButton("Add to Library")
        button.setObjectName("primaryBtn")
        button.setContentsMargins(10, 0, 10, 0)
        button.clicked.connect(lambda _, rec=item: self.add_to_library(rec))
        layout.addWidget(button)

        def _open_details(_event=None):
            self.open_book_details(item)

        card.mousePressEvent = _open_details
        cover.mousePressEvent = _open_details
        title.mousePressEvent = _open_details
        author.mousePressEvent = _open_details
        byline.mousePressEvent = _open_details
        description_lbl.mousePressEvent = _open_details

        return card

    def _get_book_detail(self, book_id):
        if not book_id:
            return None

        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                COALESCE(title, ''),
                COALESCE(authors, ''),
                COALESCE(description, ''),
                COALESCE(cover_img, '')
            FROM books
            WHERE CAST(book_id AS CHAR) = %s
            LIMIT 1
            """,
            (str(book_id),),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "title": row[0],
            "authors": row[1],
            "description": row[2],
            "cover_img": row[3],
        }

    def open_book_details(self, item):
        db_detail = self._get_book_detail(item.get("book_id"))
        payload = {
            "title": item.get("title", ""),
            "authors": "",
            "description": "",
            "cover_img": item.get("cover_img", ""),
            "rating": item.get("rating", 0),
            "status": "reading",
        }
        if db_detail:
            payload.update(db_detail)

        def _edit_book(updated_data):
            return self._save_book_details(item, payload, updated_data)

        dialog = BookDetailDialog(payload, self, edit_book_callback=_edit_book)
        dialog.exec()

    def _save_book_details(self, item, payload, updated_data):
        book_id = str(item.get("book_id") or "").strip()
        if not book_id:
            QMessageBox.warning(self, "Edit Failed", "This recommendation has no book ID.")
            return False

        title = updated_data.get("title") or payload.get("title") or item.get("title") or f"Book {book_id}"
        authors = updated_data.get("authors") or ""
        description = updated_data.get("description") or ""
        cover_img = updated_data.get("cover_img") or ""
        rating = int(updated_data.get("rating") or 1)
        status = (updated_data.get("status") or payload.get("status") or "reading").strip().lower()
        status = "completed" if status == "completed" else "reading"

        conn = connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO books (book_id, title, authors, description, genres, cover_img)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    authors = VALUES(authors),
                    description = VALUES(description),
                    cover_img = VALUES(cover_img)
                """,
                (
                    book_id,
                    title,
                    authors,
                    description,
                    None,
                    cover_img,
                ),
            )

            cursor.execute(
                "UPDATE bookshelf SET rating = %s, status = %s WHERE user_id = %s AND CAST(book_id AS CHAR) = %s",
                (rating, status, self.user_id, book_id),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            QMessageBox.warning(self, "Save Failed", f"Could not save book changes.\n{exc}")
            conn.close()
            return False
        conn.close()

        self.books_index[book_id] = title
        self.cover_index[book_id] = cover_img
        self.book_metadata_index[book_id] = {
            "authors": authors,
            "description": description,
        }
        self.title_to_book_id[title] = book_id

        payload.update(
            {
                "title": title,
                "authors": authors,
                "description": description,
                "cover_img": cover_img,
                "rating": rating,
                "status": status,
            }
        )
        QMessageBox.information(self, "Saved", "Book details updated.")
        return True

    def add_to_library(self, recommendation):
        book_id = recommendation.get("book_id")
        if not book_id:
            QMessageBox.warning(
                self,
                "Missing Book ID",
                "Could not map this title to a book_id from dataset.",
            )
            return

        conn = connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM bookshelf WHERE user_id = %s AND book_id = %s",
            (self.user_id, str(book_id)),
        )
        exists = cursor.fetchone() is not None

        if exists:
            conn.close()
            QMessageBox.information(self, "Already Added", "This book is already in your library.")
            return

        cursor.execute(
            "INSERT INTO bookshelf(user_id, book_id, rating, status) VALUES (%s, %s, %s, %s)",
            (self.user_id, str(book_id), 5, "reading"),
        )
        conn.commit()
        conn.close()

        QMessageBox.information(self, "Added", "Book added to your library.")

    def open_bookshelf(self):
        self.dashboard = DashboardWindow(self.user_id)
        show_with_parent_window_state(self, self.dashboard)
        self.close()

    def open_marketplace(self):
        from marketplace.marketplace import MarketplaceWindow

        self.marketplace = MarketplaceWindow(self.user_id)
        show_with_parent_window_state(self, self.marketplace)
        self.close()

    def open_profile_dialog(self):
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

            QPushButton#navBtn,
            QPushButton#navBtnActive {
                border: none;
                background: transparent;
                padding: 6px 10px;
                font-size: 14px;
            }

            QPushButton#navBtn {
                color: #4b5474;
            }

            QPushButton#navBtnActive {
                color: #2f66f3;
                font-weight: 600;
            }

            QLineEdit,
            QComboBox {
                background: #ffffff;
                border: 1px solid #d9deeb;
                border-radius: 10px;
                padding: 8px 10px;
            }

            QLabel#avatar {
                background: #dbe4ff;
                color: #1f3ba2;
                border-radius: 18px;
                font-weight: 700;
            }

            QFrame#recommendationBanner {
                border-radius: 16px;
                border: 1px solid #6f74f6;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4387ef,
                    stop:1 #6f37f2
                );
            }

            QLabel#bannerTitle {
                color: #ffffff;
                font-size: 34px;
                font-weight: 700;
                background: transparent;
            }

            QLabel#bannerSubtitle {
                color: #ffffff;
                font-size: 16px;
                background: transparent;
            }

            QLabel#bannerChips {
                color: #ffffff;
                font-size: 12px;
                background: transparent;
            }

            QLabel#bannerIcon {
                color: #f4f7ff;
                font-size: 24px;
                font-weight: 700;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 43px;
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

            QFrame#recCard {
                background: #ffffff;
                border: 1px solid #e3e8f3;
                border-radius: 12px;
            }

            QLabel#recCover {
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                color: #f4f7ff;
                font-size: 20px;
                font-weight: 700;
                padding: 10px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0d4367,
                    stop:1 #df6a2c
                );
            }

            QLabel#genreChip {
                color: #5a7fbe;
                background: #e7efff;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#matchLabel {
                color: #24975f;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#recTitle {
                color: #1b2133;
                font-size: 16px;
                font-weight: 600;
            }

            QLabel#recAuthor {
                color: #4c5575;
                font-size: 12px;
                font-weight: 500;
            }

            QLabel#recRating {
                color: #2e6a3c;
                font-size: 11px;
                font-weight: 600;
            }

            QLabel#recDescription {
                color: #5c6688;
                font-size: 11px;
            }

            QPushButton#primaryBtn {
                border: none;
                background: #2f66f3;
                color: #ffffff;
                border-radius: 9px;
                padding: 8px 14px;
                font-weight: 600;
                margin-left: 10px;
                margin-right: 10px;
            }

            QPushButton#mutedBtn {
                border: none;
                background: #e9ebf2;
                color: #525a72;
                border-radius: 9px;
                padding: 8px 14px;
                font-weight: 600;
            }
        """

        for title in recommendations:
            self.recommendations_list.addItem(title)


class DashboardWindow(QWidget):

    def __init__(self, user_id):
        super().__init__()

        self.user_id = user_id
        self.user_profile = get_user_profile(user_id) or {}
        self.books_index = self._load_books_index()

        self.setWindowTitle("BookNest Dashboard")
        self.resize(980, 700)
        self.setStyleSheet(self._build_stylesheet())

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(22, 14, 22, 22)
        root_layout.setSpacing(14)

        root_layout.addLayout(self._build_top_bar())
        root_layout.addWidget(self._build_hero_card())
        root_layout.addWidget(self._build_shelf_section(), 1)

        self.setLayout(root_layout)
        self.refresh_dashboard()

    def _build_top_bar(self):
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        brand = QLabel("BookNest")
        brand.setObjectName("brandTitle")
        top_bar.addWidget(brand)

        top_bar.addSpacing(12)

        self.bookshelf_nav_btn = QPushButton("Bookshelf")
        self.bookshelf_nav_btn.setObjectName("navBtnActive")
        top_bar.addWidget(self.bookshelf_nav_btn)

        self.marketplace_nav_btn = QPushButton("Marketplace")
        self.marketplace_nav_btn.setObjectName("navBtn")
        self.marketplace_nav_btn.clicked.connect(self.open_marketplace)
        top_bar.addWidget(self.marketplace_nav_btn)

        self.recommendations_nav_btn = QPushButton("Recommendations")
        self.recommendations_nav_btn.setObjectName("navBtn")
        self.recommendations_nav_btn.clicked.connect(self.open_recommendations)
        top_bar.addWidget(self.recommendations_nav_btn)

        top_bar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search books...")
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self.refresh_dashboard)
        top_bar.addWidget(self.search_input)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setObjectName("navBtn")
        self.logout_btn.clicked.connect(self.logout)
        top_bar.addWidget(self.logout_btn)

        self.avatar = ClickableAvatarLabel()
        self.avatar.setObjectName("avatar")
        self.avatar.clicked.connect(self.open_profile_dialog)
        apply_user_avatar(self.avatar, self.user_profile, self.user_id, size=36)
        top_bar.addWidget(self.avatar)

        return top_bar

    def _build_hero_card(self):
        card = QFrame()
        card.setObjectName("heroCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("My Virtual Bookshelf")
        title.setObjectName("sectionTitle")
        subtitle = QLabel("Manage your personal library and track your reading journey")
        subtitle.setObjectName("subtleText")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.scan_btn = QPushButton("Scan Book")
        self.scan_btn.setObjectName("primaryBtn")
        self.scan_btn.clicked.connect(self.show_not_implemented)
        toolbar.addWidget(self.scan_btn)

        self.add_manual_btn = QPushButton("Add Manually")
        self.add_manual_btn.setObjectName("outlineBtn")
        self.add_manual_btn.clicked.connect(self.open_add_manual_dialog)
        toolbar.addWidget(self.add_manual_btn)

        toolbar.addStretch()

        self.filter_box = QComboBox()
        self.filter_box.addItems(["All Books", "Reading", "Completed", "Wishlist"])
        self.filter_box.currentTextChanged.connect(self.refresh_dashboard)
        toolbar.addWidget(self.filter_box)

        layout.addLayout(toolbar)

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(12)
        self.stats_grid.setVerticalSpacing(12)

        self.stat_total = self._build_stat_card("Total Books", "0")
        self.stat_reading = self._build_stat_card("Currently Reading", "0")
        self.stat_completed = self._build_stat_card("Completed", "0")

        self.stats_grid.addWidget(self.stat_total, 0, 0)
        self.stats_grid.addWidget(self.stat_reading, 0, 1)
        self.stats_grid.addWidget(self.stat_completed, 0, 2)

        layout.addLayout(self.stats_grid)
        return card

    def _build_shelf_section(self):
        section = QFrame()
        section.setObjectName("shelfContainer")
        outer = QVBoxLayout(section)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(10)

        title = QLabel("Bookshelf")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        self.empty_label = QLabel("No books match your filters yet.")
        self.empty_label.setObjectName("subtleText")
        outer.addWidget(self.empty_label)

        self.shelf_scroll = QScrollArea()
        self.shelf_scroll.setWidgetResizable(True)
        self.shelf_scroll.setFrameShape(QFrame.NoFrame)

        self.shelf_content = QWidget()
        self.shelf_layout = QGridLayout(self.shelf_content)
        self.shelf_layout.setHorizontalSpacing(20)
        self.shelf_layout.setVerticalSpacing(24)
        self.shelf_layout.setContentsMargins(2, 8, 2, 8)

        self.shelf_scroll.setWidget(self.shelf_content)
        outer.addWidget(self.shelf_scroll, 1)

        return section

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

    def _load_books_index(self):
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT book_id, title FROM books WHERE title IS NOT NULL AND TRIM(title) != ''"
        )
        db_rows = cursor.fetchall()
        conn.close()

        if db_rows:
            return {str(book_id): title for book_id, title in db_rows}

        candidates = [
            Path(__file__).resolve().parent / "books_6users.csv",
            Path(__file__).resolve().parent / "books.csv",
        ]

        for path in candidates:
            if not path.exists():
                continue

            book_map = {}
            with path.open("r", encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    book_id = (row.get("book_id") or "").strip()
                    title = (row.get("title") or "").strip()
                    if book_id and title:
                        book_map[book_id] = title
            if book_map:
                return book_map

        return {}

    def _get_user_books(self):
        conn = connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                s.id,
                s.book_id,
                s.rating,
                COALESCE(s.status, 'reading'),
                COALESCE(b.title, ''),
                COALESCE(b.authors, ''),
                COALESCE(b.description, ''),
                COALESCE(b.cover_img, '')
            FROM bookshelf s
            LEFT JOIN books b ON CAST(b.book_id AS CHAR) = CAST(s.book_id AS CHAR)
            WHERE s.user_id = %s
            ORDER BY s.id DESC
            """,
            (self.user_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        books = []
        for shelf_id, book_id, rating, status, title, authors, description, cover_img in rows:
            books.append(
                {
                    "shelf_id": int(shelf_id),
                    "book_id": str(book_id),
                    "rating": rating if rating is not None else 0,
                    "status": (status or "reading").strip().lower(),
                    "title": title.strip() if title else "",
                    "authors": authors.strip() if authors else "",
                    "description": description.strip() if description else "",
                    "cover_img": cover_img or "",
                }
            )

        return books

    def refresh_dashboard(self):
        books = self._get_user_books()

        status_filter = self.filter_box.currentText().strip().lower()
        query = self.search_input.text().strip().lower()

        filtered = []
        for item in books:
            title = item["title"] or self.books_index.get(item["book_id"], f"Book {item['book_id']}")

            if status_filter != "all books" and item["status"] != status_filter:
                continue

            if query and query not in title.lower() and query not in item["book_id"].lower():
                continue

            item = dict(item)
            item["title"] = title
            filtered.append(item)

        self._update_stats(books)
        self._render_shelf_books(filtered)

    def _update_stats(self, books):
        total = len(books)
        reading = sum(1 for item in books if item["status"] == "reading")
        completed = sum(1 for item in books if item["status"] == "completed")

        self.stat_total.stat_value_label.setText(str(total))
        self.stat_reading.stat_value_label.setText(str(reading))
        self.stat_completed.stat_value_label.setText(str(completed))

    def _render_shelf_books(self, books):
        while self.shelf_layout.count():
            child = self.shelf_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

        self.empty_label.setVisible(not books)

        for index, item in enumerate(books):
            row = index // 5
            col = index % 5
            self.shelf_layout.addWidget(self._build_book_card(item), row, col)

    def _build_book_card(self, item):
        card = QFrame()
        card.setObjectName("bookCard")
        card.setFixedSize(180, 290)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            "QFrame#bookCard { background: #ffffff; border-radius: 10px; border: 1px solid #e3e8f3; }"
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(5)

        cover = CoverLabel(item.get("cover_img", ""), 145)
        layout.addWidget(cover)

        title_lbl = QLabel(item["title"])
        title_lbl.setWordWrap(True)
        title_lbl.setAlignment(Qt.AlignTop)
        title_lbl.setObjectName("bookTitle")
        title_lbl.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(title_lbl)

        author_text = (item.get("authors") or "Unknown author").split(",")[0].strip()
        author_lbl = QLabel(author_text)
        author_lbl.setWordWrap(True)
        author_lbl.setObjectName("bookMeta")
        author_lbl.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(author_lbl)

        layout.addStretch()

        status_lbl = QLabel(f"{item['status'].title()}  ★ {item.get('rating', 0)}")
        status_lbl.setObjectName("bookMeta")
        status_lbl.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(status_lbl)

        def _open_details(_event=None):
            self.open_book_details(item)

        card.mousePressEvent = _open_details
        cover.mousePressEvent = _open_details
        title_lbl.mousePressEvent = _open_details
        author_lbl.mousePressEvent = _open_details
        status_lbl.mousePressEvent = _open_details

        return card

    def open_book_details(self, item):
        payload = {
            "title": item.get("title", ""),
            "authors": item.get("authors", ""),
            "description": item.get("description", ""),
            "cover_img": item.get("cover_img", ""),
            "rating": item.get("rating", 0),
            "status": item.get("status", "reading"),
        }

        def _remove_current_book():
            return self.remove_from_shelf(item)

        def _edit_current_book(updated_data):
            return self.save_book_details(item, updated_data)

        dialog = BookDetailDialog(
            payload,
            self,
            remove_callback=_remove_current_book,
            edit_book_callback=_edit_current_book,
        )
        dialog.exec()

    def save_book_details(self, item, updated_data):
        book_id = str(item.get("book_id") or "").strip()
        if not book_id:
            QMessageBox.warning(self, "Edit Failed", "Missing book ID.")
            return False

        title = updated_data.get("title") or item.get("title") or f"Book {book_id}"
        authors = updated_data.get("authors") or ""
        description = updated_data.get("description") or ""
        cover_img = updated_data.get("cover_img") or ""
        rating = int(updated_data.get("rating") or 1)
        status = (updated_data.get("status") or item.get("status") or "reading").strip().lower()
        status = "completed" if status == "completed" else "reading"

        conn = connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO books (book_id, title, authors, description, genres, cover_img)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    authors = VALUES(authors),
                    description = VALUES(description),
                    cover_img = VALUES(cover_img)
                """,
                (
                    book_id,
                    title,
                    authors,
                    description,
                    None,
                    cover_img,
                ),
            )

            cursor.execute(
                "UPDATE bookshelf SET rating = %s, status = %s WHERE user_id = %s AND CAST(book_id AS CHAR) = %s",
                (rating, status, self.user_id, book_id),
            )

            conn.commit()
        except Exception as exc:
            conn.rollback()
            QMessageBox.warning(self, "Save Failed", f"Could not save book changes.\n{exc}")
            conn.close()
            return False
        conn.close()

        item.update(
            {
                "title": title,
                "authors": authors,
                "description": description,
                "cover_img": cover_img,
                "rating": rating,
                "status": status,
            }
        )
        self.books_index[book_id] = title
        self.refresh_dashboard()
        QMessageBox.information(self, "Saved", "Book details updated.")
        return True

    def remove_from_shelf(self, item):
        shelf_id = item.get("shelf_id")
        book_id = str(item.get("book_id") or "").strip()
        if shelf_id is None and not book_id:
            QMessageBox.warning(self, "Remove Failed", "Missing book ID.")
            return False

        title = item.get("title") or f"Book {book_id}"
        confirm = QMessageBox.question(
            self,
            "Remove Book",
            f"Remove '{title}' from your shelf?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return False

        conn = connect()
        cursor = conn.cursor()
        if shelf_id is not None:
            cursor.execute(
                "DELETE FROM bookshelf WHERE id = %s AND user_id = %s",
                (int(shelf_id), self.user_id),
            )
        else:
            cursor.execute(
                "DELETE FROM bookshelf WHERE user_id = %s AND CAST(book_id AS CHAR) = %s LIMIT 1",
                (self.user_id, book_id),
            )
        conn.commit()
        removed_count = cursor.rowcount
        conn.close()

        self.refresh_dashboard()

        if removed_count > 0:
            QMessageBox.information(self, "Removed", f"Removed '{title}' from your shelf.")
            return True
        else:
            QMessageBox.information(self, "Not Found", "That book is no longer in your shelf.")
            return False

    def _fetch_book_metadata(self, title: str, isbn: str):
        """Return metadata dict using Open Library first, then Google Books fallback."""

        def _read_json(url: str):
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "BookNest/1.0"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = response.read().decode("utf-8", errors="ignore")
            return json.loads(payload)

        def _pick_cover_from_google(volume_info: dict):
            image_links = volume_info.get("imageLinks") or {}
            return (
                image_links.get("thumbnail")
                or image_links.get("smallThumbnail")
                or ""
            ).replace("http://", "https://")

        metadata = {
            "title": title,
            "authors": "",
            "description": "",
            "cover_img": "",
            "isbn": isbn,
        }

        if isbn:
            try:
                book_data = _read_json(f"https://openlibrary.org/isbn/{isbn}.json")
                metadata["title"] = book_data.get("title") or metadata["title"]

                desc = book_data.get("description")
                if isinstance(desc, dict):
                    metadata["description"] = str(desc.get("value") or "").strip()
                elif isinstance(desc, str):
                    metadata["description"] = desc.strip()

                author_names = []
                for author in book_data.get("authors", [])[:2]:
                    key = author.get("key")
                    if not key:
                        continue
                    try:
                        author_data = _read_json(f"https://openlibrary.org{key}.json")
                        name = str(author_data.get("name") or "").strip()
                        if name:
                            author_names.append(name)
                    except Exception:
                        continue
                metadata["authors"] = ", ".join(author_names)

                covers = book_data.get("covers") or []
                if covers:
                    metadata["cover_img"] = f"https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg"
                else:
                    metadata["cover_img"] = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
            except Exception:
                pass

        if title.strip():
            try:
                query = urllib.parse.quote(title.strip())
                search_data = _read_json(f"https://openlibrary.org/search.json?title={query}&limit=1")
                docs = search_data.get("docs") or []
                if docs:
                    doc = docs[0]
                    metadata["title"] = str(doc.get("title") or metadata["title"]).strip()

                    author_names = doc.get("author_name") or []
                    if author_names:
                        metadata["authors"] = ", ".join(str(name).strip() for name in author_names[:2] if str(name).strip())

                    if not metadata["isbn"]:
                        isbns = doc.get("isbn") or []
                        if isbns:
                            metadata["isbn"] = str(isbns[0]).strip()

                    if metadata["isbn"] and not metadata["cover_img"]:
                        metadata["cover_img"] = f"https://covers.openlibrary.org/b/isbn/{metadata['isbn']}-L.jpg"
                    elif not metadata["cover_img"] and doc.get("cover_i"):
                        metadata["cover_img"] = f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg"

                    work_key = str(doc.get("key") or "").strip()
                    if work_key:
                        try:
                            work_data = _read_json(f"https://openlibrary.org{work_key}.json")
                            desc = work_data.get("description")
                            if isinstance(desc, dict):
                                metadata["description"] = str(desc.get("value") or "").strip()
                            elif isinstance(desc, str):
                                metadata["description"] = desc.strip()
                        except Exception:
                            pass
            except Exception:
                pass

        # Fallback API: Google Books (helps when Open Library has sparse metadata)
        if not metadata["authors"] or not metadata["cover_img"] or not metadata["description"]:
            try:
                if metadata["isbn"]:
                    q = urllib.parse.quote(f"isbn:{metadata['isbn']}")
                else:
                    q = urllib.parse.quote(f"intitle:{metadata['title']}")

                g_data = _read_json(
                    f"https://www.googleapis.com/books/v1/volumes?q={q}&maxResults=1"
                )
                items = g_data.get("items") or []
                if items:
                    volume_info = items[0].get("volumeInfo") or {}

                    if not metadata["title"]:
                        metadata["title"] = str(volume_info.get("title") or "").strip()

                    if not metadata["authors"]:
                        g_authors = volume_info.get("authors") or []
                        metadata["authors"] = ", ".join(
                            str(name).strip() for name in g_authors[:2] if str(name).strip()
                        )

                    if not metadata["description"]:
                        metadata["description"] = str(volume_info.get("description") or "").strip()

                    if not metadata["cover_img"]:
                        metadata["cover_img"] = _pick_cover_from_google(volume_info)
            except Exception:
                pass

        return metadata

    def open_add_manual_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Book Manually")
        dialog.setMinimumWidth(420)

        form = QFormLayout(dialog)

        title_input = QLineEdit()
        title_input.setPlaceholderText("Book title (optional if ISBN is provided)")
        form.addRow("Title", title_input)

        isbn_input = QLineEdit()
        isbn_input.setPlaceholderText("ISBN (optional)")
        form.addRow("ISBN", isbn_input)

        author_input = QLineEdit()
        author_input.setPlaceholderText("Author (optional, used if API misses)")
        form.addRow("Author", author_input)

        cover_input = QLineEdit()
        cover_input.setPlaceholderText("Cover URL (optional, used if API misses)")
        form.addRow("Cover URL", cover_input)

        rating_input = QSpinBox()
        rating_input.setRange(1, 5)
        rating_input.setValue(4)
        form.addRow("Rating", rating_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        form.addRow(buttons)

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.Accepted:
            return

        raw_title = title_input.text().strip()
        raw_isbn = isbn_input.text().strip()
        raw_author = author_input.text().strip()
        raw_cover = cover_input.text().strip()
        rating = int(rating_input.value())

        if not raw_title and not isbn:
            QMessageBox.warning(self, "Validation", "Enter a title or an ISBN.")
            return

        isbn = "".join(ch for ch in raw_isbn if ch.isdigit() or ch.upper() == "X")

        metadata = self._fetch_book_metadata(raw_title, isbn)
        final_title = (metadata.get("title") or raw_title).strip() or raw_title
        if not final_title:
            QMessageBox.warning(
                self,
                "Book Not Found",
                "Could not retrieve book metadata from ISBN. Please provide a title manually.",
            )
            return
        authors = (metadata.get("authors") or raw_author or "Unknown author").strip()
        description = (metadata.get("description") or "No description available.").strip()
        cover_img = (metadata.get("cover_img") or raw_cover or "").strip()

        # Keep manual IDs deterministic and stable across runs.
        book_id = isbn if isbn else f"manual-{zlib.crc32(final_title.lower().encode('utf-8')):08x}"
        status = "completed" if rating >= 4 else "reading"

        conn = connect()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT IGNORE INTO books (book_id, title, authors, description, genres, cover_img) VALUES (%s, %s, %s, %s, %s, %s)",
            (book_id, final_title, authors, description, None, cover_img),
        )
        cursor.execute(
            """
            UPDATE books
            SET
                title = %s,
                authors = %s,
                description = %s,
                cover_img = %s
            WHERE book_id = %s
            """,
            (final_title, authors, description, cover_img, book_id),
        )

        cursor.execute(
            "SELECT 1 FROM bookshelf WHERE user_id = %s AND book_id = %s",
            (self.user_id, str(book_id)),
        )
        exists = cursor.fetchone() is not None

        if exists:
            conn.commit()
            conn.close()
            self.refresh_dashboard()
            QMessageBox.information(self, "Already Added", "This book is already in your shelf.")
            return

        cursor.execute(
            "INSERT INTO bookshelf(user_id, book_id, rating, status) VALUES (%s, %s, %s, %s)",
            (self.user_id, str(book_id), rating, status),
        )

        conn.commit()
        conn.close()

        self.books_index[str(book_id)] = final_title
        # Make sure the user immediately sees the newly added book in the shelf.
        self.search_input.clear()
        self.filter_box.setCurrentText("All Books")
        self.refresh_dashboard()
        QMessageBox.information(self, "Added", f"Added '{final_title}' to your shelf.")

    def show_not_implemented(self):
        QMessageBox.information(self, "Coming Soon", "This action is not implemented yet.")

    def open_marketplace(self):
        from marketplace.marketplace import MarketplaceWindow

        self.marketplace = MarketplaceWindow(self.user_id)
        show_with_parent_window_state(self, self.marketplace)
        self.close()

    def open_profile_dialog(self):
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

            QPushButton#navBtn,
            QPushButton#navBtnActive {
                border: none;
                background: transparent;
                padding: 6px 10px;
                font-size: 14px;
            }

            QPushButton#navBtn {
                color: #4b5474;
            }

            QPushButton#navBtnActive {
                color: #2f66f3;
                font-weight: 600;
            }

            QLineEdit {
                background: #ffffff;
                border: 1px solid #d9deeb;
                border-radius: 10px;
                padding: 8px 10px;
            }

            QLabel#avatar {
                background: #dbe4ff;
                color: #1f3ba2;
                border-radius: 18px;
                font-weight: 700;
            }

            QFrame#heroCard,
            QFrame#shelfContainer {
                background: #ffffff;
                border: 1px solid #e3e8f3;
                border-radius: 14px;
            }

            QLabel#sectionTitle {
                font-size: 30px;
                font-weight: 700;
                color: #11162a;
            }

            QLabel#subtleText {
                color: #70799b;
                font-size: 13px;
            }

            QPushButton#primaryBtn {
                border: none;
                background: #2f66f3;
                color: #ffffff;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 600;
            }

            QPushButton#outlineBtn {
                border: 1px solid #2f66f3;
                background: #ffffff;
                color: #2f66f3;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 600;
            }

            QComboBox {
                background: #ffffff;
                border: 1px solid #d9deeb;
                border-radius: 10px;
                padding: 6px 10px;
                min-width: 120px;
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

            QLabel#bookTitle {
                font-size: 14px;
                font-weight: 600;
            }

            QLabel#bookMeta {
                font-size: 11px;
                font-weight: 500;
            }

        """

    def open_recommendations(self):

        self.rec = BookRecommendationApp(self.user_id)
        show_with_parent_window_state(self, self.rec)
        self.close()