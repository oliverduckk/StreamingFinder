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
    border: 1px solid #514b82;
}

QListWidget::item:hover {
    background-color: #20232b;
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

QLabel#providerName {
    font-size: 11pt;
    font-weight: 700;
}

QLabel#status {
    color: #b8b0e8;
}

QToolTip {
    background-color: #242731;
    color: #f2f3f5;
    border: 1px solid #343844;
}
"""
