import csv
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from database import connect, seed_user_bookshelf_from_ratings
from recommender.recommender import hybrid_recommend


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


class BookRecommendationApp(QWidget):

    def __init__(self, user_id):
        super().__init__()

        self.user_id = user_id
        seed_user_bookshelf_from_ratings(self.user_id)
        self.books_index = self._load_books_index()
        self.cover_index = self._load_cover_index()
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

        self.marketplace_nav_btn = QPushButton("Marketplace")
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

        avatar = QLabel(f"U{self.user_id}")
        avatar.setObjectName("avatar")
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(36, 36)
        top_bar.addWidget(avatar)

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
            items.append(
                {
                    "title": title,
                    "book_id": book_id,
                    "rating": meta["rating"],
                    "votes": meta["votes"],
                    "match": meta["match"],
                    "genre": meta["genre"],
                    "cover_img": self.cover_index.get(book_id, ""),
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

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(8)

        cover = CoverLabel(item.get("cover_img", ""), 145)
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
        title.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(title)

        byline = QLabel(f"Rating {item['rating']:.1f} ({item['votes']:,})")
        byline.setObjectName("subtleText")
        byline.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(byline)

        button = QPushButton("Add to Library")
        button.setObjectName("primaryBtn")
        button.setContentsMargins(10, 0, 10, 0)
        button.clicked.connect(lambda _, rec=item: self.add_to_library(rec))
        layout.addWidget(button)

        return card

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
        self.dashboard.show()
        self.close()

    def open_marketplace(self):
        from marketplace.marketplace import MarketplaceWindow

        self.marketplace = MarketplaceWindow(self.user_id)
        self.marketplace.show()
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
                color: #f4f6ff;
                font-size: 38px;
                font-weight: 700;
            }

            QLabel#bannerSubtitle {
                color: #d8e4ff;
                font-size: 19px;
            }

            QLabel#bannerChips {
                color: #d5e6ff;
                font-size: 13px;
            }

            QLabel#bannerIcon {
                color: #f4f7ff;
                font-size: 24px;
                font-weight: 700;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 43px;
            }

            QLabel#sectionTitle {
                font-size: 34px;
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
                font-size: 26px;
                font-weight: 700;
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

        avatar = QLabel(f"U{self.user_id}")
        avatar.setObjectName("avatar")
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(36, 36)
        top_bar.addWidget(avatar)

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
        self.add_manual_btn.clicked.connect(self.show_not_implemented)
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
        self.stat_high_rated = self._build_stat_card("High Rated", "0")

        self.stats_grid.addWidget(self.stat_total, 0, 0)
        self.stats_grid.addWidget(self.stat_reading, 0, 1)
        self.stats_grid.addWidget(self.stat_completed, 0, 2)
        self.stats_grid.addWidget(self.stat_high_rated, 0, 3)

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
            """,
            (self.user_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        books = []
        for book_id, rating, status, title, authors, description, cover_img in rows:
            books.append(
                {
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
        high_rated = sum(1 for item in books if int(item["rating"]) >= 4)

        self.stat_total.stat_value_label.setText(str(total))
        self.stat_reading.stat_value_label.setText(str(reading))
        self.stat_completed.stat_value_label.setText(str(completed))
        self.stat_high_rated.stat_value_label.setText(str(high_rated))

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

        return card

    def show_not_implemented(self):
        QMessageBox.information(self, "Coming Soon", "This action is not implemented yet.")

    def open_marketplace(self):
        from marketplace.marketplace import MarketplaceWindow

        self.marketplace = MarketplaceWindow(self.user_id)
        self.marketplace.show()
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
        self.rec.show()
        self.close()