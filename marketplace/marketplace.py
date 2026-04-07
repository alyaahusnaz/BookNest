import ast
import csv
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from database import connect, get_user_profile
from profile import ClickableAvatarLabel, ProfileDialog, apply_user_avatar
from recommender.recommender import hybrid_recommend_score_map
from window_state import show_with_parent_window_state


class CoverLabel(QLabel):
    """Async cover image: shows a placeholder then swaps in the real image."""

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
            w = self.width() if self.width() > 0 else 220
            scaled = pixmap.scaled(w, self.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.setPixmap(scaled)


def post_book(seller_id, book_id, price):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO marketplace(seller_id,book_id,price) VALUES (%s,%s,%s)",
        (seller_id, book_id, price)
    )

    conn.commit()
    conn.close()


def browse_marketplace():

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT seller_id, book_id, price FROM marketplace")

    books = cursor.fetchall()

    conn.close()

    return books


class MarketplaceWindow(QWidget):

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        self.market_section = "my"
        self._my_has_items = False
        self._other_has_items = False
        self._hybrid_match_map = {}
        self.user_profile = get_user_profile(user_id) or {}
        self.books_index = self._load_books_index()
        self.book_metadata_index = self._load_book_metadata_index()

        self.setWindowTitle("BookNest Marketplace")
        self.resize(980, 700)
        self.setStyleSheet(self._build_stylesheet())

        root = QVBoxLayout()
        root.setContentsMargins(22, 14, 22, 22)
        root.setSpacing(14)

        root.addLayout(self._build_top_bar())
        root.addLayout(self._build_content())

        self.setLayout(root)
        self.refresh_cards()

    def _build_top_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(10)

        brand = QLabel("BookNest")
        brand.setObjectName("brandTitle")
        bar.addWidget(brand)
        bar.addSpacing(12)

        self.bookshelf_btn = QPushButton("Bookshelf")
        self.bookshelf_btn.setObjectName("navBtn")
        self.bookshelf_btn.clicked.connect(self.open_bookshelf)
        bar.addWidget(self.bookshelf_btn)

        self.marketplace_btn = QPushButton("Marketplace")
        self.marketplace_btn.setObjectName("navBtnActive")
        bar.addWidget(self.marketplace_btn)

        self.rec_btn = QPushButton("Recommendations")
        self.rec_btn.setObjectName("navBtn")
        self.rec_btn.clicked.connect(self.open_recommendations)
        bar.addWidget(self.rec_btn)

        bar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search books...")
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self.refresh_cards)
        bar.addWidget(self.search_input)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setObjectName("navBtn")
        self.logout_btn.clicked.connect(self.logout)
        bar.addWidget(self.logout_btn)

        bell = QLabel("🔔")
        bell.setObjectName("iconChip")
        bell.setAlignment(Qt.AlignCenter)
        bell.setFixedSize(34, 34)
        bar.addWidget(bell)

        self.avatar = ClickableAvatarLabel()
        self.avatar.setObjectName("avatar")
        self.avatar.clicked.connect(self.open_profile_dialog)
        apply_user_avatar(self.avatar, self.user_profile, self.user_id, size=36)
        bar.addWidget(self.avatar)

        return bar

    def _build_content(self):
        row = QHBoxLayout()
        row.setSpacing(16)

        row.addWidget(self._build_left_filters(), 1)
        row.addWidget(self._build_right_market(), 3)

        return row

    def _build_left_filters(self):
        card = QFrame()
        card.setObjectName("sideCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = QLabel("Filters & Preferences")
        title.setObjectName("smallHeader")
        layout.addWidget(title)

        genre_label = QLabel("Preferred Genres")
        genre_label.setObjectName("fieldLabel")
        layout.addWidget(genre_label)

        self.genre_box = QComboBox()
        self.genre_box.addItems(["All Genres", "Fiction", "Mystery", "Self Help", "Romance"])
        self.genre_box.currentTextChanged.connect(self.refresh_cards)
        layout.addWidget(self.genre_box)

        cond_label = QLabel("Book Condition")
        cond_label.setObjectName("fieldLabel")
        layout.addWidget(cond_label)

        self.condition_box = QComboBox()
        self.condition_box.addItems(["All Conditions", "Like New", "Very Good", "Good"])
        self.condition_box.currentTextChanged.connect(self.refresh_cards)
        layout.addWidget(self.condition_box)

        price_label = QLabel("Max Price (RM)")
        price_label.setObjectName("fieldLabel")
        layout.addWidget(price_label)

        self.max_price = QDoubleSpinBox()
        self.max_price.setRange(0.0, 9999.0)
        self.max_price.setValue(100.0)
        self.max_price.valueChanged.connect(self.refresh_cards)
        layout.addWidget(self.max_price)

        type_label = QLabel("Exchange Type")
        type_label.setObjectName("fieldLabel")
        layout.addWidget(type_label)

        self.swap_only = QRadioButton("Book Swap")
        self.sell_only = QRadioButton("For Sale")
        self.both_types = QRadioButton("Both")
        self.both_types.setChecked(True)
        self.swap_only.toggled.connect(self.refresh_cards)
        self.sell_only.toggled.connect(self.refresh_cards)
        self.both_types.toggled.connect(self.refresh_cards)

        layout.addWidget(self.swap_only)
        layout.addWidget(self.sell_only)
        layout.addWidget(self.both_types)

        layout.addStretch()
        return card

    def _build_right_market(self):
        container = QVBoxLayout()
        container.setSpacing(12)

        header = QHBoxLayout()
        header.addStretch()

        self.list_btn = QPushButton("+ List a Book")
        self.list_btn.setObjectName("primaryBtn")
        self.list_btn.clicked.connect(self.list_a_book)
        header.addWidget(self.list_btn)
        container.addLayout(header)

        banner = QFrame()
        banner.setObjectName("matchBanner")
        b_layout = QVBoxLayout(banner)
        b_layout.setContentsMargins(16, 14, 16, 14)
        b_layout.setSpacing(4)
        b_title = QLabel("Exchange & Marketplace")
        b_title.setObjectName("bannerTitle")
        b_sub = QLabel("Discover and trade books with readers near you")
        b_sub.setObjectName("bannerSub")
        b_layout.addWidget(b_title)
        b_layout.addWidget(b_sub)
        container.addWidget(banner)

        toolbar = QHBoxLayout()
        available = QLabel("Marketplace Listings")
        available.setObjectName("smallHeader")
        toolbar.addWidget(available)
        toolbar.addStretch()

        self.sort_box = QComboBox()
        self.sort_box.addItems(["Sort by Price", "Sort by Match"])
        self.sort_box.currentTextChanged.connect(self.refresh_cards)
        toolbar.addWidget(self.sort_box)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("primaryBtn")
        refresh_btn.clicked.connect(self.refresh_cards)
        toolbar.addWidget(refresh_btn)
        container.addLayout(toolbar)

        section_tabs = QHBoxLayout()
        section_tabs.setSpacing(8)

        self.my_market_btn = QPushButton("My Marketplace")
        self.my_market_btn.clicked.connect(lambda: self._set_market_section("my"))
        section_tabs.addWidget(self.my_market_btn)

        self.other_market_btn = QPushButton("Other Marketplace")
        self.other_market_btn.clicked.connect(lambda: self._set_market_section("other"))
        section_tabs.addWidget(self.other_market_btn)

        section_tabs.addStretch()
        container.addLayout(section_tabs)

        self.my_header = QLabel("My Marketplace (My Books For Sale/Swap)")
        self.my_header.setObjectName("fieldLabel")
        container.addWidget(self.my_header)

        self.my_empty_label = QLabel("You have no listings that match current filters.")
        self.my_empty_label.setObjectName("subtleText")
        container.addWidget(self.my_empty_label)

        self.my_scroll = QScrollArea()
        self.my_scroll.setWidgetResizable(True)
        self.my_scroll.setFrameShape(QFrame.NoFrame)
        self.my_grid_host = QWidget()
        self.my_cards_grid = QGridLayout(self.my_grid_host)
        self.my_cards_grid.setContentsMargins(1, 1, 1, 1)
        self.my_cards_grid.setHorizontalSpacing(14)
        self.my_cards_grid.setVerticalSpacing(14)
        self.my_scroll.setWidget(self.my_grid_host)
        container.addWidget(self.my_scroll, 1)

        self.other_header = QLabel("Other Marketplace (Books From Other Users)")
        self.other_header.setObjectName("fieldLabel")
        container.addWidget(self.other_header)

        self.other_empty_label = QLabel("No other-user listings match current filters.")
        self.other_empty_label.setObjectName("subtleText")
        container.addWidget(self.other_empty_label)

        self.other_scroll = QScrollArea()
        self.other_scroll.setWidgetResizable(True)
        self.other_scroll.setFrameShape(QFrame.NoFrame)
        self.other_grid_host = QWidget()
        self.other_cards_grid = QGridLayout(self.other_grid_host)
        self.other_cards_grid.setContentsMargins(1, 1, 1, 1)
        self.other_cards_grid.setHorizontalSpacing(14)
        self.other_cards_grid.setVerticalSpacing(14)
        self.other_scroll.setWidget(self.other_grid_host)
        container.addWidget(self.other_scroll, 1)

        load_more = QPushButton("Load More Books")
        load_more.setObjectName("mutedBtn")
        load_more.clicked.connect(self.refresh_cards)
        container.addWidget(load_more, alignment=Qt.AlignHCenter)

        shell = QFrame()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.addLayout(container)

        self._set_market_section(self.market_section)
        return shell

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
            Path(__file__).resolve().parents[1] / "books_6users.csv",
            Path(__file__).resolve().parents[1] / "books.csv",
        ]

        for file_path in candidates:
            if not file_path.exists():
                continue

            result = {}
            with file_path.open("r", encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    book_id = (row.get("book_id") or "").strip()
                    title = (row.get("title") or "").strip()
                    if book_id and title:
                        result[book_id] = title

            if result:
                return result

        return {}

    def _load_book_metadata_index(self):
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                book_id,
                COALESCE(authors, ''),
                COALESCE(description, ''),
                COALESCE(cover_img, ''),
                COALESCE(genres, '')
            FROM books
            """
        )
        rows = cursor.fetchall()
        conn.close()

        result = {}
        for book_id, authors, description, cover_img, genres in rows:
            result[str(book_id)] = {
                "authors": (authors or "").strip(),
                "description": (description or "").strip(),
                "cover_img": (cover_img or "").strip(),
                "genres": (genres or "").strip(),
            }
        return result

    def _genre_matches(self, raw_genres, selected_genre):
        if selected_genre == "all genres":
            return True

        target = "".join(ch for ch in selected_genre.lower() if ch.isalnum())
        if not target:
            return True

        text = (raw_genres or "").strip()
        genres = []

        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = ast.literal_eval(text)
                if isinstance(parsed, list):
                    genres = [str(value).strip() for value in parsed if str(value).strip()]
            except (ValueError, SyntaxError):
                pass

        if not genres:
            genres = [part.strip().strip("'\"") for part in text.strip("[]").split(",") if part.strip()]

        for genre in genres:
            normalized = "".join(ch for ch in genre.lower() if ch.isalnum())
            if target in normalized or normalized in target:
                return True

        return False

    def _get_market_items(self):
        rows = browse_marketplace()
        self._hybrid_match_map = hybrid_recommend_score_map(self.user_id, exclude_read=False)

        max_score = max(self._hybrid_match_map.values()) if self._hybrid_match_map else 0.0

        items = []
        for seller_id, book_id, price in rows:
            book_id_text = str(book_id)
            title = self.books_index.get(book_id_text, f"Book {book_id_text}")
            metadata = self.book_metadata_index.get(book_id_text, {})
            raw_score = self._hybrid_match_map.get(book_id_text, 0.0)
            if max_score > 0:
                match = int(round((raw_score / max_score) * 100))
                match = max(0, min(100, match))
            else:
                match = 0
            distance = 1.0 + (abs(hash(book_id_text + "d")) % 30) / 10
            condition_set = ["Like New", "Very Good", "Good"]
            condition = condition_set[abs(hash(book_id_text + "c")) % len(condition_set)]

            items.append(
                {
                    "seller_id": seller_id,
                    "book_id": book_id_text,
                    "title": title,
                    "authors": metadata.get("authors") or "Unknown author",
                    "description": metadata.get("description") or "No description available.",
                    "cover_img": metadata.get("cover_img") or "",
                    "genres": metadata.get("genres") or "",
                    "price": float(price) if price is not None else 0.0,
                    "match": match,
                    "distance": distance,
                    "condition": condition,
                }
            )

        return items

    def _get_user_bookshelf_choices(self):
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                CAST(s.book_id AS CHAR),
                COALESCE(NULLIF(b.title, ''), '')
            FROM bookshelf s
            LEFT JOIN books b ON CAST(b.book_id AS CHAR) = CAST(s.book_id AS CHAR)
            WHERE s.user_id = %s
            ORDER BY s.id DESC
            """,
            (self.user_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        choices = []
        seen_book_ids = set()
        for book_id, title in rows:
            book_id_text = str(book_id)
            if book_id_text in seen_book_ids:
                continue
            seen_book_ids.add(book_id_text)

            title_text = (title or "").strip() or self.books_index.get(book_id_text, f"Book {book_id_text}")
            choices.append({"book_id": book_id_text, "title": title_text})

        return choices

    def refresh_cards(self):
        items = self._get_market_items()

        query = self.search_input.text().strip().lower()
        max_price = self.max_price.value()
        condition_filter = self.condition_box.currentText().strip().lower()
        genre_filter = self.genre_box.currentText().strip().lower()

        filtered = []
        for item in items:
            if query and query not in item["title"].lower() and query not in item["book_id"].lower():
                continue

            if item["price"] > max_price:
                continue

            if condition_filter != "all conditions" and item["condition"].lower() != condition_filter:
                continue

            if not self._genre_matches(item.get("genres", ""), genre_filter):
                continue

            if self.swap_only.isChecked() and item["price"] > 0:
                continue

            if self.sell_only.isChecked() and item["price"] <= 0:
                continue

            filtered.append(item)

        selected_sort = self.sort_box.currentText()
        if selected_sort == "Sort by Price":
            filtered.sort(key=lambda x: x["price"])
        else:
            filtered.sort(key=lambda x: x["match"], reverse=True)

        my_items = [item for item in filtered if int(item["seller_id"]) == int(self.user_id)]
        other_items = [item for item in filtered if int(item["seller_id"]) != int(self.user_id)]

        self._my_has_items = bool(my_items)
        self._other_has_items = bool(other_items)

        self._render_cards(self.my_cards_grid, self.my_empty_label, my_items)
        self._render_cards(self.other_cards_grid, self.other_empty_label, other_items)
        self._apply_market_section_visibility()

    def _set_market_section(self, section):
        if section not in {"my", "other"}:
            return
        self.market_section = section
        self._apply_market_section_visibility()

        if hasattr(self, "my_market_btn") and hasattr(self, "other_market_btn"):
            if section == "my":
                self.my_market_btn.setObjectName("scopeBtnActive")
                self.other_market_btn.setObjectName("scopeBtn")
            else:
                self.my_market_btn.setObjectName("scopeBtn")
                self.other_market_btn.setObjectName("scopeBtnActive")

            self.my_market_btn.style().unpolish(self.my_market_btn)
            self.my_market_btn.style().polish(self.my_market_btn)
            self.other_market_btn.style().unpolish(self.other_market_btn)
            self.other_market_btn.style().polish(self.other_market_btn)

    def _apply_market_section_visibility(self):
        is_my = self.market_section == "my"

        if hasattr(self, "my_header"):
            self.my_header.setVisible(is_my)
        if hasattr(self, "my_empty_label"):
            self.my_empty_label.setVisible(is_my and not self._my_has_items)
        if hasattr(self, "my_scroll"):
            self.my_scroll.setVisible(is_my)

        if hasattr(self, "other_header"):
            self.other_header.setVisible(not is_my)
        if hasattr(self, "other_empty_label"):
            self.other_empty_label.setVisible((not is_my) and not self._other_has_items)
        if hasattr(self, "other_scroll"):
            self.other_scroll.setVisible(not is_my)

    def _render_cards(self, target_grid, target_empty_label, items):
        while target_grid.count():
            child = target_grid.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

        target_empty_label.setVisible(not items)

        for idx, item in enumerate(items):
            row = idx // 3
            col = idx % 3
            target_grid.addWidget(self._build_book_card(item), row, col)

    def _build_book_card(self, item):
        card = QFrame()
        card.setObjectName("bookCard")
        card.setFixedSize(270, 380)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(6)

        cover = CoverLabel(item.get("cover_img", ""), 140)
        cover.setObjectName("cover")
        layout.addWidget(cover)

        is_my_listing = int(item.get("seller_id", -1)) == int(self.user_id)
        if not is_my_listing:
            stats_row = QHBoxLayout()
            match_chip = QLabel(f"{item['match']}% Match")
            match_chip.setObjectName("matchChip")
            stats_row.addWidget(match_chip)
            stats_row.addStretch()
            stats_row.setContentsMargins(8, 0, 8, 0)
            layout.addLayout(stats_row)

        title = QLabel(item["title"])
        title.setObjectName("cardTitle")
        title.setWordWrap(True)
        title.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(title)

        author_name = (item.get("authors") or "Unknown author").split(",")[0].strip()
        author = QLabel(f"by {author_name}")
        author.setObjectName("subtleText")
        author.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(author)

        description = item.get("description") or "No description available."
        if len(description) > 96:
            description = description[:93].rstrip() + "..."
        description_label = QLabel(description)
        description_label.setObjectName("cardDesc")
        description_label.setWordWrap(True)
        description_label.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(description_label)

        seller = QLabel(f"Seller U{item['seller_id']}")
        seller.setObjectName("distanceText")
        seller.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(seller)

        layout.addStretch()

        foot = QHBoxLayout()
        cond = QLabel(item["condition"])
        cond.setObjectName("condChip")
        foot.addWidget(cond)
        foot.addStretch()

        price = "Swap Only" if item["price"] <= 0 else f"RM{item['price']:.2f}"
        price_label = QLabel(price)
        price_label.setObjectName("priceTag")
        foot.addWidget(price_label)
        foot.setContentsMargins(8, 0, 8, 0)
        layout.addLayout(foot)

        return card

    def list_a_book(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("List A Book")
        dialog.setText("Fill in book listing details.")
        dialog.setIcon(QMessageBox.Information)

        choices = self._get_user_bookshelf_choices()
        if not choices:
            QMessageBox.information(
                self,
                "No Shelf Books",
                "Add a book to your shelf first, then list it in the marketplace.",
            )
            return

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(8)

        title_input = QComboBox()
        title_input.setEditable(True)
        title_input.setInsertPolicy(QComboBox.NoInsert)
        for choice in choices:
            title_input.addItem(choice["title"], choice["book_id"])

        completer = QCompleter([choice["title"] for choice in choices], title_input)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        title_input.setCompleter(completer)

        price_input = QDoubleSpinBox()
        price_input.setRange(0.0, 9999.0)
        price_input.setValue(0.0)

        form.addRow("Book Title:", title_input)
        form.addRow("Price (RM, 0=swap):", price_input)

        dialog.layout().addWidget(form_widget, 1, 0, 1, dialog.layout().columnCount())
        dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        if dialog.exec() != QMessageBox.Ok:
            return

        selected_text = title_input.currentText().strip()
        book_id = title_input.currentData()
        for choice in choices:
            if book_id:
                break
            if selected_text.lower() == choice["title"].lower():
                book_id = choice["book_id"]
                break

        if not book_id:
            QMessageBox.warning(
                self,
                "Invalid Book",
                "Select a valid title from your bookshelf list.",
            )
            return

        conn = connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO marketplace(seller_id, book_id, price) VALUES (%s, %s, %s)",
            (self.user_id, book_id, float(price_input.value())),
        )
        conn.commit()
        conn.close()

        self.refresh_cards()

    def open_bookshelf(self):
        from dashboard import DashboardWindow

        self.dashboard = DashboardWindow(self.user_id)
        show_with_parent_window_state(self, self.dashboard)
        self.close()

    def open_recommendations(self):
        from dashboard import BookRecommendationApp

        self.recommendations = BookRecommendationApp(self.user_id)
        show_with_parent_window_state(self, self.recommendations)
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
            QComboBox,
            QDoubleSpinBox {
                background: #ffffff;
                border: 1px solid #d9deeb;
                border-radius: 8px;
                padding: 6px 8px;
            }

            QRadioButton {
                spacing: 8px;
                color: #171b27;
            }

            QRadioButton::indicator {
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 2px solid #7a839f;
                background: #f1f3f8;
            }

            QRadioButton::indicator:checked {
                border: 2px solid #565f78;
                background: #727b92;
            }

            QLabel#avatar,
            QLabel#iconChip {
                background: #dbe4ff;
                color: #1f3ba2;
                border-radius: 17px;
                font-weight: 700;
            }

            QLabel#avatar {
                border: 1px solid #d1dbfb;
            }

            QFrame#sideCard,
            QFrame#bookCard {
                background: #ffffff;
                border: 1px solid #e3e8f3;
                border-radius: 12px;
            }

            QFrame#matchBanner {
                border-radius: 16px;
                border: 1px solid #6f74f6;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3f8ef8,
                    stop:1 #6d3df0
                );
            }

            QLabel#mainHeader {
                font-size: 36px;
                font-weight: 700;
                color: #11162a;
            }

            QLabel#smallHeader {
                font-size: 26px;
                font-weight: 700;
                color: #222a40;
            }

            QLabel#fieldLabel {
                font-size: 12px;
                font-weight: 600;
                color: #3e4765;
            }

            QLabel#subtleText {
                color: #70799b;
                font-size: 12px;
            }

            QLabel#bannerTitle {
                background: transparent;
                color: #f4f6ff;
                font-size: 28px;
                font-weight: 700;
            }

            QLabel#bannerSub {
                background: transparent;
                color: #dfebff;
                font-size: 13px;
            }

            QLabel#chip {
                color: #f7fbff;
                background: rgba(255, 255, 255, 0.25);
                border-radius: 8px;
                padding: 6px 10px;
                font-weight: 600;
            }

            QPushButton#primaryBtn {
                border: none;
                background: #4758f5;
                color: #ffffff;
                border-radius: 9px;
                padding: 8px 14px;
                font-weight: 600;
            }

            QPushButton#primaryDarkBtn {
                border: none;
                background: #0f1c35;
                color: #ffffff;
                border-radius: 9px;
                padding: 8px 14px;
                font-weight: 600;
            }

            QPushButton#mutedBtn {
                border: none;
                background: #e9ebf2;
                color: #525a72;
                border-radius: 9px;
                padding: 8px 14px;
                font-weight: 600;
            }

            QPushButton#scopeBtn,
            QPushButton#scopeBtnActive {
                border-radius: 9px;
                padding: 8px 12px;
                font-weight: 600;
            }

            QPushButton#scopeBtn {
                border: 1px solid #d7dced;
                background: #ffffff;
                color: #415075;
            }

            QPushButton#scopeBtnActive {
                border: 1px solid #4758f5;
                background: #4758f5;
                color: #ffffff;
            }

            QLabel#cover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #165d73,
                    stop:1 #eb8f3e
                );
                border-top-left-radius: 11px;
                border-top-right-radius: 11px;
                color: #fefefe;
                font-size: 16px;
                font-weight: 700;
                padding: 10px;
            }

            QLabel#matchChip {
                color: #2f8752;
                background: #d9f3e2;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#distanceText {
                color: #727a96;
                font-size: 11px;
            }

            QLabel#cardTitle {
                color: #1a2134;
                font-size: 16px;
                font-weight: 700;
            }

            QLabel#cardDesc {
                color: #5c6688;
                font-size: 11px;
            }

            QLabel#condChip {
                color: #5d7f48;
                background: #ebf5e6;
                border-radius: 7px;
                padding: 2px 8px;
                font-size: 11px;
            }

            QLabel#priceTag {
                color: #2a59dd;
                font-size: 17px;
                font-weight: 700;
            }
        """