from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QComboBox,
)

from database import connect


def register_user(username, password, favorite_genre, favorite_author):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO users(username, password, favorite_genre, favorite_author)
        VALUES (%s, %s, %s, %s)
        """,
        (username, password, favorite_genre, favorite_author),
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

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Username"))
        self.username_input = QLineEdit()
        layout.addWidget(self.username_input)

        layout.addWidget(QLabel("Password"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        genres, authors = get_registration_options()

        layout.addWidget(QLabel("Favorite Genre"))
        self.genre_box = QComboBox()
        self.genre_box.addItem("Select a genre")
        self.genre_box.addItems(genres)
        layout.addWidget(self.genre_box)

        layout.addWidget(QLabel("Favorite Author"))
        self.author_box = QComboBox()
        self.author_box.addItem("Select an author")
        self.author_box.addItems(authors)
        layout.addWidget(self.author_box)

        self.register_button = QPushButton("Create Account")
        self.register_button.clicked.connect(self.handle_register)
        layout.addWidget(self.register_button)

        self.back_button = QPushButton("Back to Login")
        self.back_button.clicked.connect(self.open_login)
        layout.addWidget(self.back_button)

        self.setLayout(layout)

    def handle_register(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        favorite_genre = self.genre_box.currentText().strip()
        favorite_author = self.author_box.currentText().strip()

        if not username or not password:
            QMessageBox.warning(self, "Validation", "Username and password are required.")
            return

        if favorite_genre == "Select a genre" or favorite_author == "Select an author":
            QMessageBox.warning(
                self,
                "Validation",
                "Please choose your favorite genre and author.",
            )
            return

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
        self.login.show()
        self.close()