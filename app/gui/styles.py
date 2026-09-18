APP_STYLESHEET = """
QWidget {
    background-color: #101116;
    color: #f2f3f5;
    font-family: "Segoe UI";
    font-size: 10pt;
}

QMainWindow {
    background-color: #101116;
}

QFrame#panel {
    background-color: #17191f;
    border: 1px solid #2a2d35;
    border-radius: 12px;
}

QFrame#providerCard {
    background-color: #15171d;
    border: 1px solid #2d3040;
    border-radius: 11px;
}

QFrame#providerCard:hover {
    border: 1px solid #4f477d;
}

QFrame#emptyState {
    background-color: #15171d;
    border: 1px dashed #343844;
    border-radius: 10px;
}

QLabel#appTitle {
    font-size: 24pt;
    font-weight: 700;
}

QLabel#muted {
    color: #9da3af;
}

QLabel#sectionTitle {
    font-size: 11pt;
    font-weight: 700;
}

QLabel#mediaTitle {
    font-size: 22pt;
    font-weight: 700;
}

QLabel#posterFrame {
    color: #8f95a3;
    background-color: #20232b;
    border: 1px solid #30343e;
    border-radius: 10px;
}

QLabel#providerName {
    font-size: 11pt;
    font-weight: 700;
}

QLabel#providerLogo {
    color: #ded9ff;
    background-color: #232131;
    border: 1px solid #4d4677;
    border-radius: 9px;
    font-size: 13pt;
    font-weight: 700;
}

QLabel#countryChip {
    color: #ded9ff;
    background-color: #242133;
    border: 1px solid #3f3962;
    border-radius: 8px;
    padding: 5px 8px;
}

QLabel#status {
    color: #b8b0e8;
}

QLineEdit {
    background-color: #17191f;
    border: 1px solid #343844;
    border-radius: 10px;
    padding: 10px 12px;
    selection-background-color: #7667e8;
}

QLineEdit:focus {
    border: 1px solid #8274f2;
}

QPushButton {
    background-color: #242731;
    border: 1px solid #343844;
    border-radius: 10px;
    padding: 9px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #2d303c;
}

QPushButton[accent="true"] {
    background-color: #6f61dc;
    border: 1px solid #8274f2;
}

QPushButton[accent="true"]:hover {
    background-color: #7b6ce8;
}

QPushButton#countryMoreButton {
    color: #c9c2ff;
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 2px;
    font-weight: 600;
}

QPushButton#countryMoreButton:hover {
    color: #f0edff;
    background-color: #232131;
}

QPushButton:disabled {
    color: #686d78;
    background-color: #1a1c22;
}

QCheckBox {
    spacing: 8px;
    padding: 4px 6px;
}

QCheckBox:checked {
    color: #ded9ff;
}

QListWidget {
    background-color: #17191f;
    border: none;
    outline: 0;
}

QListWidget::item {
    border-bottom: 1px solid #292c34;
    padding: 8px;
    border-radius: 7px;
}

QListWidget::item:selected {
    background-color: #2b2940;
    border: 1px solid #625a99;
}

QListWidget::item:hover {
    background-color: #20232b;
}

QProgressBar#loadingBar {
    background: transparent;
    border: none;
    border-radius: 1px;
}

QProgressBar#loadingBar::chunk {
    background-color: #7b6ce8;
    border-radius: 1px;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #514b82;
    min-height: 30px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #6f61dc;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QSplitter::handle {
    background: #242731;
    width: 1px;
}

QToolTip {
    background-color: #242731;
    color: #f2f3f5;
    border: 1px solid #514b82;
}

/* Personal library controls */
QComboBox#libraryStatus {
    background-color: #1b1d25;
    border: 1px solid #3b3f4d;
    border-radius: 8px;
    padding: 6px 10px;
    min-width: 120px;
}

QComboBox#libraryStatus:focus {
    border: 1px solid #8274f2;
}

QComboBox#libraryStatus::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background-color: #1b1d25;
    color: #f2f3f5;
    selection-background-color: #2b2940;
    border: 1px solid #514b82;
}

QCheckBox#favouriteToggle:checked {
    color: #d8d1ff;
    font-weight: 700;
}

"""

# Rating dialog styles appended in V0.8
APP_STYLESHEET += """
QLabel#ratingSummary {
    color: #d8d1ff;
    font-weight: 700;
}

QPushButton#rateButton {
    color: #ded9ff;
    background-color: #242133;
    border: 1px solid #4f477d;
    padding: 6px 11px;
}

QPushButton#rateButton:hover {
    background-color: #302b46;
    border: 1px solid #7667e8;
}

QLabel#ratingDialogTitle {
    font-size: 18pt;
    font-weight: 700;
}

QLabel#ratingTotal {
    color: #d8d1ff;
    font-size: 20pt;
    font-weight: 800;
}

QDoubleSpinBox#ratingScore {
    background-color: #1b1d25;
    border: 1px solid #3b3f4d;
    border-radius: 8px;
    padding: 6px 8px;
    min-width: 90px;
}

QDoubleSpinBox#ratingScore:focus {
    border: 1px solid #8274f2;
}

QPlainTextEdit#ratingNotes {
    background-color: #17191f;
    border: 1px solid #343844;
    border-radius: 10px;
    padding: 9px;
    selection-background-color: #7667e8;
}

QPlainTextEdit#ratingNotes:focus {
    border: 1px solid #8274f2;
}
"""

# Library navigation and poster-grid styles appended in V0.9
APP_STYLESHEET += """
QPushButton#navButton {
    color: #aeb3bf;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 7px 15px;
    font-weight: 700;
}

QPushButton#navButton:hover {
    color: #f2efff;
    background-color: #1c1d26;
    border: 1px solid #353748;
}

QPushButton#navButton[active="true"] {
    color: #f2efff;
    background-color: #2b2940;
    border: 1px solid #6f61dc;
}

QLabel#libraryHeading {
    font-size: 18pt;
    font-weight: 750;
}

QComboBox#libraryFilter {
    background-color: #1b1d25;
    border: 1px solid #3b3f4d;
    border-radius: 8px;
    padding: 8px 10px;
    min-width: 125px;
}

QComboBox#libraryFilter:focus {
    border: 1px solid #8274f2;
}

QComboBox#libraryFilter::drop-down {
    border: none;
    width: 22px;
}

QCheckBox#libraryFavouriteFilter {
    color: #d8d1ff;
    padding: 7px 8px;
}

QFrame#libraryCard {
    background-color: #17191f;
    border: 1px solid #2d3040;
    border-radius: 12px;
}

QFrame#libraryCard:hover {
    background-color: #1b1d25;
    border: 1px solid #625a99;
}

QLabel#libraryPoster {
    color: #8f95a3;
    background-color: #111218;
    border: 1px solid #30343e;
    border-radius: 9px;
}

QLabel#libraryCardTitle {
    font-size: 11pt;
    font-weight: 700;
}

QLabel#libraryStatusBadge {
    color: #d8d1ff;
    background-color: #242133;
    border: 1px solid #403a66;
    border-radius: 7px;
    padding: 3px 7px;
    font-weight: 600;
}

QLabel#libraryFavouriteBadge {
    color: #e7e2ff;
    background-color: #302a49;
    border: 1px solid #5d5296;
    border-radius: 7px;
    padding: 3px 7px;
    font-weight: 700;
}

QLabel#libraryCardRating {
    color: #cfc7ff;
    font-size: 12pt;
    font-weight: 800;
}

QPushButton#libraryOpenButton {
    color: #ded9ff;
    background-color: #242133;
    border: 1px solid #4f477d;
    border-radius: 8px;
    padding: 7px 10px;
    font-weight: 650;
}

QPushButton#libraryOpenButton:hover {
    background-color: #302b46;
    border: 1px solid #7667e8;
}

QFrame#libraryEmptyState {
    background-color: #15171d;
    border: 1px dashed #4f477d;
    border-radius: 12px;
    min-width: 520px;
}
"""
