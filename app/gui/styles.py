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
"""
