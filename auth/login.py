import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QApplication,
    QMessageBox,
)

from database import connect
from dashboard import DashboardWindow
from window_state import show_with_parent_window_state


def login_user(username: str, password: str):
    """Return the user row (id, username, password) if credentials match."""

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    conn.close()

    if user and user[2] == password:
        return user

    return None


class LoginWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("BookNest Login")
        self.resize(980, 700)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Username"))

        self.username_input = QLineEdit()
        layout.addWidget(self.username_input)

        layout.addWidget(QLabel("Password"))

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        self.login_button = QPushButton("Login")
        layout.addWidget(self.login_button)

        self.register_button = QPushButton("Register")
        layout.addWidget(self.register_button)

        self.setLayout(layout)

        # connect button
        self.login_button.clicked.connect(self.handle_login)
        self.register_button.clicked.connect(self.open_register)

    def handle_login(self):
        username = self.username_input.text()
        password = self.password_input.text()
        user = login_user(username, password)
        if user:
            user_id = user[0]
            self.dashboard = DashboardWindow(user_id)
            show_with_parent_window_state(self, self.dashboard)
            self.close()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password")

    def open_register(self):
        from auth.register import RegisterWindow

        self.register = RegisterWindow()
        show_with_parent_window_state(self, self.register)
        self.close()


if __name__ == "__main__":
    # Ensure database schema exists
    from database import create_tables

    create_tables()

    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec())