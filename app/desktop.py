import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.paths import bundled_resource_path
from app.gui.main_window import MainWindow
from app.gui.styles import APP_STYLESHEET
from app.runtime.api_server import EmbeddedApiServer


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("StreamingFinder")
    app.setOrganizationName("StreamingFinder")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

    icon_path = bundled_resource_path("assets", "streamingfinder.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    api_server = EmbeddedApiServer()
    try:
        api_server.start()
    except RuntimeError as exc:
        QMessageBox.warning(
            None,
            "StreamingFinder API unavailable",
            f"{exc}\n\nThe desktop app will continue to open normally.",
        )

    app.aboutToQuit.connect(api_server.stop)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
