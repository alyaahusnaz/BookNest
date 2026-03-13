import csv
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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

from database import connect


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

    cursor.execute("SELECT seller_id, book_id, price, COALESCE(location, 'Unknown') FROM marketplace")

    books = cursor.fetchall()

    conn.close()

    return books


class MarketplaceWindow(QWidget):

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        self.books_index = self._load_books_index()

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

        bell = QLabel("🔔")
        bell.setObjectName("iconChip")
        bell.setAlignment(Qt.AlignCenter)
        bell.setFixedSize(34, 34)
        bar.addWidget(bell)

        avatar = QLabel(f"U{self.user_id}")
        avatar.setObjectName("avatar")
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(36, 36)
        bar.addWidget(avatar)

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

        loc_label = QLabel("Location")
        loc_label.setObjectName("fieldLabel")
        layout.addWidget(loc_label)

        self.location_input = QLineEdit("Gelugor, Penang")
        self.location_input.textChanged.connect(self.refresh_cards)
        layout.addWidget(self.location_input)

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

        apply_btn = QPushButton("Apply Filters")
        apply_btn.setObjectName("primaryDarkBtn")
        apply_btn.clicked.connect(self.refresh_cards)
        layout.addWidget(apply_btn)

        layout.addStretch()
        return card

    def _build_right_market(self):
        container = QVBoxLayout()
        container.setSpacing(12)

        header = QHBoxLayout()
        heading_block = QVBoxLayout()
        heading = QLabel("Exchange & Marketplace")
        heading.setObjectName("mainHeader")
        subtitle = QLabel("Discover and trade books with readers near you")
        subtitle.setObjectName("subtleText")
        heading_block.addWidget(heading)
        heading_block.addWidget(subtitle)
        header.addLayout(heading_block)
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
        b_title = QLabel("Smart Geo-Preference Matches")
        b_title.setObjectName("bannerTitle")
        b_sub = QLabel("Books that match your taste preferences and are available nearby")
        b_sub.setObjectName("bannerSub")
        self.location_chip = QLabel("Gelugor, Penang")
        self.location_chip.setObjectName("chip")
        b_layout.addWidget(b_title)
        b_layout.addWidget(b_sub)
        b_layout.addWidget(self.location_chip, alignment=Qt.AlignRight)
        container.addWidget(banner)

        toolbar = QHBoxLayout()
        available = QLabel("All Available Books")
        available.setObjectName("smallHeader")
        toolbar.addWidget(available)
        toolbar.addStretch()

        self.sort_box = QComboBox()
        self.sort_box.addItems(["Sort by Distance", "Sort by Price", "Sort by Match"])
        self.sort_box.currentTextChanged.connect(self.refresh_cards)
        toolbar.addWidget(self.sort_box)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("primaryBtn")
        refresh_btn.clicked.connect(self.refresh_cards)
        toolbar.addWidget(refresh_btn)
        container.addLayout(toolbar)

        self.empty_label = QLabel("No marketplace books match your filters.")
        self.empty_label.setObjectName("subtleText")
        container.addWidget(self.empty_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.grid_host = QWidget()
        self.cards_grid = QGridLayout(self.grid_host)
        self.cards_grid.setContentsMargins(1, 1, 1, 1)
        self.cards_grid.setHorizontalSpacing(14)
        self.cards_grid.setVerticalSpacing(14)

        self.scroll.setWidget(self.grid_host)
        container.addWidget(self.scroll, 1)

        load_more = QPushButton("Load More Books")
        load_more.setObjectName("mutedBtn")
        load_more.clicked.connect(self.refresh_cards)
        container.addWidget(load_more, alignment=Qt.AlignHCenter)

        shell = QFrame()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.addLayout(container)
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

    def _get_market_items(self):
        rows = browse_marketplace()
        items = []
        for seller_id, book_id, price, location in rows:
            book_id_text = str(book_id)
            title = self.books_index.get(book_id_text, f"Book {book_id_text}")
            match = 82 + (abs(hash(book_id_text)) % 17)
            distance = 1.0 + (abs(hash(book_id_text + "d")) % 30) / 10
            condition_set = ["Like New", "Very Good", "Good"]
            condition = condition_set[abs(hash(book_id_text + "c")) % len(condition_set)]

            items.append(
                {
                    "seller_id": seller_id,
                    "book_id": book_id_text,
                    "title": title,
                    "price": float(price) if price is not None else 0.0,
                    "location": location or "Unknown",
                    "match": match,
                    "distance": distance,
                    "condition": condition,
                }
            )

        return items

    def refresh_cards(self):
        self.location_chip.setText(self.location_input.text().strip() or "Unknown")
        items = self._get_market_items()

        query = self.search_input.text().strip().lower()
        location_filter = self.location_input.text().strip().lower()
        max_price = self.max_price.value()
        condition_filter = self.condition_box.currentText().strip().lower()

        filtered = []
        for item in items:
            if query and query not in item["title"].lower() and query not in item["book_id"].lower():
                continue

            if location_filter and location_filter not in item["location"].lower():
                continue

            if item["price"] > max_price:
                continue

            if condition_filter != "all conditions" and item["condition"].lower() != condition_filter:
                continue

            if self.swap_only.isChecked() and item["price"] > 0:
                continue

            if self.sell_only.isChecked() and item["price"] <= 0:
                continue

            filtered.append(item)

        selected_sort = self.sort_box.currentText()
        if selected_sort == "Sort by Price":
            filtered.sort(key=lambda x: x["price"])
        elif selected_sort == "Sort by Match":
            filtered.sort(key=lambda x: x["match"], reverse=True)
        else:
            filtered.sort(key=lambda x: x["distance"])

        self._render_cards(filtered)

    def _render_cards(self, items):
        while self.cards_grid.count():
            child = self.cards_grid.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

        self.empty_label.setVisible(not items)

        for idx, item in enumerate(items):
            row = idx // 3
            col = idx % 3
            self.cards_grid.addWidget(self._build_book_card(item), row, col)

    def _build_book_card(self, item):
        card = QFrame()
        card.setObjectName("bookCard")
        card.setMinimumWidth(190)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(6)

        cover = QLabel(item["title"])
        cover.setObjectName("cover")
        cover.setWordWrap(True)
        cover.setAlignment(Qt.AlignCenter)
        cover.setFixedHeight(150)
        layout.addWidget(cover)

        stats_row = QHBoxLayout()
        match_chip = QLabel(f"{item['match']}% Match")
        match_chip.setObjectName("matchChip")
        distance = QLabel(f"{item['distance']:.1f} km away")
        distance.setObjectName("distanceText")
        stats_row.addWidget(match_chip)
        stats_row.addStretch()
        stats_row.addWidget(distance)
        stats_row.setContentsMargins(8, 0, 8, 0)
        layout.addLayout(stats_row)

        title = QLabel(item["title"])
        title.setObjectName("cardTitle")
        title.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(title)

        author = QLabel(f"Seller U{item['seller_id']} • {item['location']}")
        author.setObjectName("subtleText")
        author.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(author)

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

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(8)

        book_id_input = QLineEdit()
        price_input = QDoubleSpinBox()
        price_input.setRange(0.0, 9999.0)
        price_input.setValue(0.0)
        location_input = QLineEdit(self.location_input.text().strip() or "Gelugor, Penang")

        form.addRow("Book ID:", book_id_input)
        form.addRow("Price (RM, 0=swap):", price_input)
        form.addRow("Location:", location_input)

        dialog.layout().addWidget(form_widget, 1, 0, 1, dialog.layout().columnCount())
        dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        if dialog.exec() != QMessageBox.Ok:
            return

        book_id = book_id_input.text().strip()
        if not book_id:
            QMessageBox.warning(self, "Missing Book ID", "Book ID is required.")
            return

        conn = connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO marketplace(seller_id, book_id, price, location) VALUES (%s, %s, %s, %s)",
            (self.user_id, book_id, float(price_input.value()), location_input.text().strip() or "Unknown"),
        )
        conn.commit()
        conn.close()

        self.refresh_cards()

    def open_bookshelf(self):
        from dashboard import DashboardWindow

        self.dashboard = DashboardWindow(self.user_id)
        self.dashboard.show()
        self.close()

    def open_recommendations(self):
        from dashboard import BookRecommendationApp

        self.recommendations = BookRecommendationApp(self.user_id)
        self.recommendations.show()
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

            QLabel#avatar,
            QLabel#iconChip {
                background: #dbe4ff;
                color: #1f3ba2;
                border-radius: 17px;
                font-weight: 700;
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
                color: #f4f6ff;
                font-size: 28px;
                font-weight: 700;
            }

            QLabel#bannerSub {
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
                font-size: 20px;
                font-weight: 700;
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