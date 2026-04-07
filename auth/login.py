import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
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

    cursor.execute("SELECT id, username, password, role FROM users WHERE username = %s", (username,))
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
        self.setMinimumSize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)

        wrapper = QHBoxLayout()
        wrapper.addStretch(1)

        card = QFrame()
        card.setObjectName("loginCard")
        card.setMaximumWidth(520)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 30, 34, 30)
        card_layout.setSpacing(12)

        title = QLabel("Welcome to BookNest")
        title.setObjectName("titleLabel")
        card_layout.addWidget(title)

        subtitle = QLabel("Sign in to continue to your dashboard")
        subtitle.setObjectName("subtitleLabel")
        card_layout.addWidget(subtitle)

        user_label = QLabel("Username")
        user_label.setObjectName("fieldLabel")
        card_layout.addWidget(user_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        card_layout.addWidget(self.username_input)

        pass_label = QLabel("Password")
        pass_label.setObjectName("fieldLabel")
        card_layout.addWidget(pass_label)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter your password")
        card_layout.addWidget(self.password_input)

        self.login_button = QPushButton("Login")
        self.login_button.setObjectName("loginButton")
        card_layout.addWidget(self.login_button)

        self.register_button = QPushButton("Register")
        self.register_button.setObjectName("registerButton")
        card_layout.addWidget(self.register_button)

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
            #loginCard {
                background: #ffffff;
                border: 1px solid #d6dce8;
                border-radius: 14px;
            }
            #titleLabel {
                font-size: 28px;
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
            QLineEdit {
                border: 1px solid #cdd5e3;
                border-radius: 8px;
                padding: 10px 12px;
                background: #fcfdff;
            }
            QLineEdit:focus {
                border: 1px solid #2f6fdb;
            }
            QPushButton {
                border: none;
                border-radius: 8px;
                min-height: 38px;
                font-weight: 600;
            }
            #loginButton {
                margin-top: 8px;
                background: #245dc9;
                color: white;
            }
            #loginButton:hover {
                background: #1e50ac;
            }
            #registerButton {
                background: #e8edf7;
                color: #233252;
            }
            #registerButton:hover {
                background: #dbe4f4;
            }
            """
        )

        # connect button
        self.login_button.clicked.connect(self.handle_login)
        self.register_button.clicked.connect(self.open_register)

    def handle_login(self):
        username = self.username_input.text()
        password = self.password_input.text()
        user = login_user(username, password)
        if user:
            user_id = user[0]
            role = (user[3] or "user").strip().lower()
            if role == "admin":
                from admin import AdminWindow

                self.admin = AdminWindow(user_id)
                show_with_parent_window_state(self, self.admin)
            else:
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