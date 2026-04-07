from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QComboBox,
)

from database import connect
from window_state import show_with_parent_window_state


def register_user(username, password, favorite_genre, favorite_author):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO users(username, password, favorite_genre, favorite_author, shelf_initialized)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (username, password, favorite_genre, favorite_author, 1),
    )

    conn.commit()
    conn.close()


def get_registration_options():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT genres FROM books WHERE genres IS NOT NULL AND TRIM(genres) != ''")
    raw_genres = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT authors FROM books WHERE authors IS NOT NULL AND TRIM(authors) != ''")
    raw_authors = [row[0] for row in cursor.fetchall()]

    conn.close()

    genres = set()
    for entry in raw_genres:
        text = str(entry).strip().strip("[]")
        for part in text.split(","):
            cleaned = part.strip().strip("'\"")
            if cleaned:
                genres.add(cleaned)

    authors = set()
    for entry in raw_authors:
        for part in str(entry).split(","):
            cleaned = part.strip()
            if cleaned:
                authors.add(cleaned)

    return sorted(genres), sorted(authors)


class RegisterWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("BookNest Register")
        self.resize(980, 700)
        self.setMinimumSize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)

        wrapper = QHBoxLayout()
        wrapper.addStretch(1)

        card = QFrame()
        card.setObjectName("registerCard")
        card.setMaximumWidth(560)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(12)

        title = QLabel("Create Your BookNest Account")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        subtitle = QLabel("Set up your profile to get better recommendations.")
        subtitle.setObjectName("subtitleLabel")
        layout.addWidget(subtitle)

        username_label = QLabel("Username")
        username_label.setObjectName("fieldLabel")
        layout.addWidget(username_label)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Choose a username")
        layout.addWidget(self.username_input)

        password_label = QLabel("Password")
        password_label.setObjectName("fieldLabel")
        layout.addWidget(password_label)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Create a password")
        layout.addWidget(self.password_input)

        genres, authors = get_registration_options()

        genre_label = QLabel("Favorite Genre")
        genre_label.setObjectName("fieldLabel")
        layout.addWidget(genre_label)
        self.genre_box = QComboBox()
        self.genre_box.addItem("Select a genre")
        self.genre_box.addItems(genres)
        layout.addWidget(self.genre_box)

        author_label = QLabel("Favorite Author")
        author_label.setObjectName("fieldLabel")
        layout.addWidget(author_label)
        self.author_box = QComboBox()
        self.author_box.addItem("Select an author")
        self.author_box.addItems(authors)
        layout.addWidget(self.author_box)

        self.register_button = QPushButton("Create Account")
        self.register_button.setObjectName("primaryButton")
        self.register_button.clicked.connect(self.handle_register)
        layout.addWidget(self.register_button)

        self.back_button = QPushButton("Back to Login")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.open_login)
        layout.addWidget(self.back_button)

        wrapper.addWidget(card)
        wrapper.addStretch(1)
        root.addStretch(1)
        root.addLayout(wrapper)
        root.addStretch(1)

        self.setStyleSheet(
            """
            QWidget {
                background-color: #f1f4f9;
                color: #1d2438;
                font-size: 13px;
            }
            #registerCard {
                background: #ffffff;
                border: 1px solid #d6dce8;
                border-radius: 14px;
            }
            #titleLabel {
                font-size: 26px;
                font-weight: 700;
                color: #11172b;
                padding-bottom: 2px;
            }
            #subtitleLabel {
                font-size: 13px;
                color: #4e5977;
                padding-bottom: 8px;
            }
            #fieldLabel {
                font-weight: 600;
                color: #273252;
                padding-top: 4px;
            }
            QLineEdit,
            QComboBox {
                border: 1px solid #cdd5e3;
                border-radius: 8px;
                padding: 10px 12px;
                background: #fcfdff;
            }
            QLineEdit:focus,
            QComboBox:focus {
                border: 1px solid #2f6fdb;
            }
            QPushButton {
                border: none;
                border-radius: 8px;
                min-height: 38px;
                font-weight: 600;
            }
            #primaryButton {
                margin-top: 8px;
                background: #245dc9;
                color: white;
            }
            #primaryButton:hover {
                background: #1e50ac;
            }
            #secondaryButton {
                background: #e8edf7;
                color: #233252;
            }
            #secondaryButton:hover {
                background: #dbe4f4;
            }
            """
        )

    def handle_register(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        favorite_genre = self.genre_box.currentText().strip()
        favorite_author = self.author_box.currentText().strip()

        if not username or not password:
            QMessageBox.warning(self, "Validation", "Username and password are required.")
            return

        if favorite_genre == "Select a genre":
            favorite_genre = ""

        if favorite_author == "Select an author":
            favorite_author = ""

        try:
            register_user(username, password, favorite_genre, favorite_author)
        except Exception as exc:
            QMessageBox.warning(self, "Registration Failed", str(exc))
            return

        QMessageBox.information(self, "Success", "Account created. Please login.")
        self.open_login()

    def open_login(self):
        from auth.login import LoginWindow

        self.login = LoginWindow()
        show_with_parent_window_state(self, self.login)
        self.close()