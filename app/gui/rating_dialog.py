from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.media import MediaRating
from app.services.rating_system import RATING_CATEGORIES, rating_total


class RatingDialog(QDialog):
    """Edit the ten-category personal rating for a movie or TV series."""

    def __init__(
        self,
        title: str,
        existing: MediaRating | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Rate {title}")
        self.setModal(True)
        self.resize(520, 680)
        self.setMinimumWidth(480)
        self._spinboxes: dict[str, QDoubleSpinBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("ratingDialogTitle")
        heading.setWordWrap(True)
        root.addWidget(heading)

        intro = QLabel(
            "Score each category out of 10. The ten categories combine into "
            "your overall /100 rating."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        root.addWidget(intro)

        total_row = QHBoxLayout()
        total_row.addWidget(QLabel("Overall rating"))
        total_row.addStretch()
        self.total_label = QLabel("50.0 / 100")
        self.total_label.setObjectName("ratingTotal")
        total_row.addWidget(self.total_label)
        root.addLayout(total_row)

        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        existing_scores = (
            {category.key: category.score for category in existing.categories}
            if existing is not None
            else {}
        )
        for category in RATING_CATEGORIES:
            spinbox = QDoubleSpinBox()
            spinbox.setObjectName("ratingScore")
            spinbox.setRange(0.0, 10.0)
            spinbox.setSingleStep(0.5)
            spinbox.setDecimals(1)
            spinbox.setValue(existing_scores.get(category.key, 5.0))
            spinbox.valueChanged.connect(self._update_total)
            self._spinboxes[category.key] = spinbox
            form.addRow(category.label, spinbox)

        root.addLayout(form)

        notes_label = QLabel("Notes")
        notes_label.setObjectName("sectionTitle")
        root.addWidget(notes_label)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setObjectName("ratingNotes")
        self.notes_edit.setPlaceholderText(
            "Optional thoughts — what worked, what didn't, favourite moments, "
            "anything Mairon should know later…"
        )
        self.notes_edit.setPlainText(existing.notes or "" if existing is not None else "")
        self.notes_edit.setMinimumHeight(110)
        root.addWidget(self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Save rating")
            save_button.setProperty("accent", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._update_total()

    def scores(self) -> dict[str, float]:
        return {key: spinbox.value() for key, spinbox in self._spinboxes.items()}

    def notes(self) -> str | None:
        value = self.notes_edit.toPlainText().strip()
        return value or None

    def _update_total(self, _value: float | None = None) -> None:
        self.total_label.setText(f"{rating_total(self.scores()):.1f} / 100")
