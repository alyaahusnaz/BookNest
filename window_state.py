from PySide6.QtWidgets import QWidget


def show_with_parent_window_state(source: QWidget, target: QWidget):
    """Show target window using source window geometry/state."""

    if source.isFullScreen():
        target.showFullScreen()
        return

    if source.isMaximized():
        target.showMaximized()
        return

    geometry = source.geometry()
    if geometry.width() > 0 and geometry.height() > 0:
        target.setGeometry(geometry)

    target.show()