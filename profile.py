from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from database import get_user_profile, update_user_profile


def _build_avatar_text(username, user_id):
    cleaned = "".join(ch for ch in (username or "") if ch.isalnum())
    if cleaned:
        return cleaned[:2].upper()
    return f"U{user_id}"


def _build_circular_pixmap(image_path, size):
    if not image_path:
        return None

    path = Path(image_path)
    if not path.exists():
        return None

    source = QPixmap(str(path))
    if source.isNull():
        return None

    scaled = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    masked = QPixmap(size, size)
    masked.fill(Qt.transparent)

    painter = QPainter(masked)
    painter.setRenderHint(QPainter.Antialiasing, True)

    clip_path = QPainterPath()
    clip_path.addEllipse(0, 0, size, size)
    painter.setClipPath(clip_path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()

    return masked


def apply_user_avatar(label, user_profile, user_id, size=36):
    username = ""
    profile_image = ""
    if user_profile:
        username = user_profile.get("username") or ""
        profile_image = user_profile.get("profile_image") or ""

    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignCenter)

    pixmap = _build_circular_pixmap(profile_image, size)
    if pixmap is not None:
        label.setText("")
        label.setPixmap(pixmap)
        return

    label.setPixmap(QPixmap())
    label.setText(_build_avatar_text(username, user_id))


class ClickableAvatarLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ProfileDialog(QDialog):
    def __init__(self, user_id, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.user_profile = get_user_profile(user_id) or {}
        self.profile_image_path = (self.user_profile.get("profile_image") or "").strip()
        self.saved_profile = None

        self.setWindowTitle("Edit Profile")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        header = QLabel("Update your profile")
        header.setStyleSheet("font-size: 22px; font-weight: 700; color: #171b27;")
        layout.addWidget(header)

        avatar_row = QHBoxLayout()
        avatar_row.setSpacing(12)

        self.avatar_preview = QLabel()
        self.avatar_preview.setObjectName("avatar")
        apply_user_avatar(self.avatar_preview, self.user_profile, self.user_id, size=88)
        avatar_row.addWidget(self.avatar_preview, 0, Qt.AlignTop)

        avatar_controls = QVBoxLayout()
        avatar_controls.setSpacing(8)

        choose_image_btn = QPushButton("Choose Profile Image")
        choose_image_btn.clicked.connect(self._choose_image)
        avatar_controls.addWidget(choose_image_btn)

        clear_image_btn = QPushButton("Remove Image")
        clear_image_btn.clicked.connect(self._clear_image)
        avatar_controls.addWidget(clear_image_btn)

        self.image_path_label = QLabel(self.profile_image_path or "No image selected")
        self.image_path_label.setWordWrap(True)
        self.image_path_label.setStyleSheet("color: #70799b; font-size: 12px;")
        avatar_controls.addWidget(self.image_path_label)
        avatar_controls.addStretch()

        avatar_row.addLayout(avatar_controls, 1)
        layout.addLayout(avatar_row)

        form = QFormLayout()
        form.setSpacing(10)

        self.username_input = QLineEdit((self.user_profile.get("username") or "").strip())
        self.username_input.textChanged.connect(self._refresh_preview)
        form.addRow("Username", self.username_input)

        self.favorite_genre_input = QLineEdit((self.user_profile.get("favorite_genre") or "").strip())
        self.favorite_genre_input.setPlaceholderText("e.g. Fantasy")
        form.addRow("Favorite Genre", self.favorite_genre_input)

        self.favorite_author_input = QLineEdit((self.user_profile.get("favorite_author") or "").strip())
        self.favorite_author_input.setPlaceholderText("e.g. Agatha Christie")
        form.addRow("Favorite Author", self.favorite_author_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Leave blank to keep current password")
        form.addRow("New Password", self.password_input)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        self.confirm_password_input.setPlaceholderText("Re-enter new password")
        form.addRow("Confirm Password", self.confirm_password_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._handle_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Profile Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not file_path:
            return

        self.profile_image_path = file_path
        self._refresh_preview()

    def _clear_image(self):
        self.profile_image_path = ""
        self._refresh_preview()

    def _refresh_preview(self):
        profile_data = {
            "username": self.username_input.text().strip() or self.user_profile.get("username") or "",
            "profile_image": self.profile_image_path,
        }
        apply_user_avatar(self.avatar_preview, profile_data, self.user_id, size=88)
        self.image_path_label.setText(self.profile_image_path or "No image selected")

    def _handle_save(self):
        username = self.username_input.text().strip()
        favorite_genre = self.favorite_genre_input.text().strip()
        favorite_author = self.favorite_author_input.text().strip()
        new_password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()

        if not username:
            QMessageBox.warning(self, "Validation", "Username is required.")
            return

        if new_password or confirm_password:
            if new_password != confirm_password:
                QMessageBox.warning(self, "Validation", "Passwords do not match.")
                return
            if len(new_password) < 4:
                QMessageBox.warning(self, "Validation", "Password must be at least 4 characters.")
                return

        password_to_save = new_password or self.user_profile.get("password") or ""
        if not password_to_save:
            QMessageBox.warning(self, "Validation", "Password is required.")
            return

        try:
            update_user_profile(
                self.user_id,
                username,
                password_to_save,
                self.profile_image_path,
                favorite_genre,
                favorite_author,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Validation", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return

        self.saved_profile = get_user_profile(self.user_id)
        self.accept()