import sys
from PySide6.QtWidgets import QApplication
from auth.login import LoginWindow
from database import create_tables


if __name__ == "__main__":

    create_tables()

    app = QApplication(sys.argv)

    window = LoginWindow()
    window.show()

    sys.exit(app.exec())