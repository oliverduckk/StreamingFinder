from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer, QUrl, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.clients.tmdb import TMDBClient
from app.core.config import get_settings
from app.db.database import SQLiteDatabase
from app.gui.helpers import (
    media_subtitle,
    poster_url,
    provider_logo_url,
    split_country_preview,
)
from app.gui.rating_dialog import RatingDialog
from app.gui.workers import AsyncWorker
from app.models.media import (
    LibraryStatus,
    MediaAvailability,
    MediaLibraryEntry,
    MediaRating,
    MediaSearchResult,
    StreamingServiceAvailability,
)
from app.repositories.library import MediaLibraryRepository
from app.repositories.preferences import StreamingPreferencesRepository
from app.repositories.ratings import MediaRatingRepository
from app.services.library_catalog import prepare_library_entries, rating_totals
from app.services.streaming_services import STREAMING_SERVICES


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings()
        self.tmdb = TMDBClient(self.settings)
        database = SQLiteDatabase(self.settings.database_path)
        self.preferences = StreamingPreferencesRepository(database)
        self.library = MediaLibraryRepository(database)
        self.ratings = MediaRatingRepository(database)
        self.thread_pool = QThreadPool.globalInstance()
        self.network = QNetworkAccessManager(self)
        self.current_media: MediaSearchResult | None = None
        self.service_checkboxes: dict[str, QCheckBox] = {}
        self._availability_generation = 0
        self._active_operations = 0
        self._library_dirty = True
        self._preference_refresh_timer = QTimer(self)
        self._preference_refresh_timer.setSingleShot(True)
        self._preference_refresh_timer.setInterval(250)
        self._preference_refresh_timer.timeout.connect(self._refresh_current_availability)

        self.setWindowTitle("StreamingFinder")
        self.resize(1280, 820)
        self.setMinimumSize(1000, 680)

        self._build_ui()
        self._load_saved_services()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 20, 24, 18)
        root_layout.setSpacing(14)

        header = QHBoxLayout()
        header_text = QVBoxLayout()
        title = QLabel("StreamingFinder")
        title.setObjectName("appTitle")
        subtitle = QLabel("Find it. Track it. Rate it. Know where to stream it.")
        subtitle.setObjectName("muted")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header.addLayout(header_text)
        header.addStretch()
        root_layout.addLayout(header)

        navigation = QHBoxLayout()
        navigation.setSpacing(8)
        self.search_nav_button = QPushButton("Search")
        self.search_nav_button.setObjectName("navButton")
        self.search_nav_button.clicked.connect(self._show_search_page)
        self.library_nav_button = QPushButton("Library")
        self.library_nav_button.setObjectName("navButton")
        self.library_nav_button.clicked.connect(self._show_library_page)
        navigation.addWidget(self.search_nav_button)
        navigation.addWidget(self.library_nav_button)
        navigation.addStretch()
        root_layout.addLayout(navigation)

        self.page_stack = QStackedWidget()
        self.search_page = self._build_search_page()
        self.library_page = self._build_library_page()
        self.page_stack.addWidget(self.search_page)
        self.page_stack.addWidget(self.library_page)
        root_layout.addWidget(self.page_stack, 1)

        self.setCentralWidget(root)
        self._show_search_page()

    def _build_search_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)

        services_panel = QFrame()
        services_panel.setObjectName("panel")
        services_layout = QVBoxLayout(services_panel)
        services_layout.setContentsMargins(16, 13, 16, 13)
        services_layout.setSpacing(8)

        services_heading = QHBoxLayout()
        services_title = QLabel("My streaming services")
        services_title.setObjectName("sectionTitle")
        services_hint = QLabel("Changes save automatically")
        services_hint.setObjectName("muted")
        services_heading.addWidget(services_title)
        services_heading.addStretch()
        services_heading.addWidget(services_hint)
        services_layout.addLayout(services_heading)

        service_grid = QGridLayout()
        service_grid.setHorizontalSpacing(18)
        service_grid.setVerticalSpacing(4)
        for index, service in enumerate(STREAMING_SERVICES):
            checkbox = QCheckBox(service.name)
            checkbox.setProperty("service_key", service.key)
            checkbox.stateChanged.connect(self._on_service_selection_changed)
            self.service_checkboxes[service.key] = checkbox
            service_grid.addWidget(checkbox, index // 4, index % 4)
        services_layout.addLayout(service_grid)
        page_layout.addWidget(services_panel)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search movies and TV shows…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self._start_search)
        self.search_button = QPushButton("Search")
        self.search_button.setProperty("accent", True)
        self.search_button.clicked.connect(self._start_search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        page_layout.addLayout(search_row)

        self.status_label = QLabel("Search for a movie or show to get started.")
        self.status_label.setObjectName("status")
        page_layout.addWidget(self.status_label)

        self.loading_bar = QProgressBar()
        self.loading_bar.setObjectName("loadingBar")
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(3)
        self.loading_bar.hide()
        page_layout.addWidget(self.loading_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        results_panel = QFrame()
        results_panel.setObjectName("panel")
        results_layout = QVBoxLayout(results_panel)
        results_layout.setContentsMargins(12, 12, 12, 12)
        results_layout.setSpacing(8)
        results_heading = QLabel("Search results")
        results_heading.setObjectName("sectionTitle")
        results_layout.addWidget(results_heading)

        self.results_list = QListWidget()
        self.results_list.setIconSize(QSize(64, 96))
        self.results_list.setSpacing(2)
        self.results_list.itemClicked.connect(self._on_result_selected)
        results_layout.addWidget(self.results_list, 1)
        splitter.addWidget(results_panel)

        details_panel = QFrame()
        details_panel.setObjectName("panel")
        details_outer_layout = QVBoxLayout(details_panel)
        details_outer_layout.setContentsMargins(0, 0, 0, 0)

        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        details_scroll_widget = QWidget()
        self.details_layout = QVBoxLayout(details_scroll_widget)
        self.details_layout.setContentsMargins(20, 20, 20, 18)
        self.details_layout.setSpacing(14)

        media_header = QHBoxLayout()
        media_header.setSpacing(18)
        self.poster_label = QLabel("No poster")
        self.poster_label.setObjectName("posterFrame")
        self.poster_label.setFixedSize(220, 330)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        media_header.addWidget(self.poster_label, 0, Qt.AlignmentFlag.AlignTop)

        media_text = QVBoxLayout()
        media_text.setSpacing(8)
        self.media_title_label = QLabel("Select a result")
        self.media_title_label.setObjectName("mediaTitle")
        self.media_title_label.setWordWrap(True)
        self.media_meta_label = QLabel("")
        self.media_meta_label.setObjectName("muted")
        self.media_overview_label = QLabel(
            "Streaming availability and title details will appear here."
        )
        self.media_overview_label.setWordWrap(True)
        self.media_overview_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.media_overview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        media_text.addWidget(self.media_title_label)
        media_text.addWidget(self.media_meta_label)

        library_row = QHBoxLayout()
        library_row.setSpacing(10)
        library_label = QLabel("Library")
        library_label.setObjectName("muted")
        self.library_status_combo = QComboBox()
        self.library_status_combo.setObjectName("libraryStatus")
        self.library_status_combo.addItem("Not in library", "")
        self.library_status_combo.addItem("Watchlist", "watchlist")
        self.library_status_combo.addItem("Watching", "watching")
        self.library_status_combo.addItem("Watched", "watched")
        self.library_status_combo.addItem("Dropped", "dropped")
        self.library_status_combo.setEnabled(False)
        self.library_status_combo.currentIndexChanged.connect(
            self._on_library_status_changed
        )
        self.favourite_checkbox = QCheckBox("Favourite")
        self.favourite_checkbox.setObjectName("favouriteToggle")
        self.favourite_checkbox.setEnabled(False)
        self.favourite_checkbox.stateChanged.connect(self._on_favourite_changed)
        library_row.addWidget(library_label)
        library_row.addWidget(self.library_status_combo)
        library_row.addWidget(self.favourite_checkbox)
        library_row.addStretch()
        media_text.addLayout(library_row)

        rating_row = QHBoxLayout()
        rating_row.setSpacing(10)
        rating_label = QLabel("My rating")
        rating_label.setObjectName("muted")
        self.rating_summary_label = QLabel("Not rated")
        self.rating_summary_label.setObjectName("ratingSummary")
        self.rate_button = QPushButton("Rate")
        self.rate_button.setObjectName("rateButton")
        self.rate_button.setEnabled(False)
        self.rate_button.clicked.connect(self._open_rating_dialog)
        rating_row.addWidget(rating_label)
        rating_row.addWidget(self.rating_summary_label)
        rating_row.addWidget(self.rate_button)
        rating_row.addStretch()
        media_text.addLayout(rating_row)

        media_text.addSpacing(4)
        media_text.addWidget(self.media_overview_label)
        media_text.addStretch()
        media_header.addLayout(media_text, 1)
        self.details_layout.addLayout(media_header)

        availability_title = QLabel("Streaming availability")
        availability_title.setObjectName("sectionTitle")
        self.details_layout.addWidget(availability_title)

        self.providers_container = QWidget()
        self.providers_layout = QVBoxLayout(self.providers_container)
        self.providers_layout.setContentsMargins(0, 0, 0, 0)
        self.providers_layout.setSpacing(10)
        self._set_provider_message("Select a title to check your services.")
        self.details_layout.addWidget(self.providers_container)
        self.details_layout.addStretch()

        attribution = QLabel(
            "Metadata: TMDB • Streaming availability: JustWatch via TMDB\n"
            "This product uses the TMDB API but is not endorsed or certified by TMDB."
        )
        attribution.setObjectName("muted")
        attribution.setWordWrap(True)
        self.details_layout.addWidget(attribution)

        details_scroll.setWidget(details_scroll_widget)
        details_outer_layout.addWidget(details_scroll)
        splitter.addWidget(details_panel)
        splitter.setSizes([360, 820])
        page_layout.addWidget(splitter, 1)
        return page

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        toolbar = QFrame()
        toolbar.setObjectName("panel")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 14, 16, 14)
        toolbar_layout.setSpacing(10)

        heading_row = QHBoxLayout()
        heading_text = QVBoxLayout()
        heading = QLabel("My library")
        heading.setObjectName("libraryHeading")
        self.library_summary_label = QLabel("Your saved movies and shows will appear here.")
        self.library_summary_label.setObjectName("muted")
        heading_text.addWidget(heading)
        heading_text.addWidget(self.library_summary_label)
        heading_row.addLayout(heading_text)
        heading_row.addStretch()
        toolbar_layout.addLayout(heading_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(9)
        self.library_search_input = QLineEdit()
        self.library_search_input.setPlaceholderText("Filter your library…")
        self.library_search_input.setClearButtonEnabled(True)
        self.library_search_input.textChanged.connect(self._refresh_library_view)

        self.library_status_filter = QComboBox()
        self.library_status_filter.setObjectName("libraryFilter")
        self.library_status_filter.addItem("All statuses", "")
        self.library_status_filter.addItem("Watchlist", "watchlist")
        self.library_status_filter.addItem("Watching", "watching")
        self.library_status_filter.addItem("Watched", "watched")
        self.library_status_filter.addItem("Dropped", "dropped")
        self.library_status_filter.currentIndexChanged.connect(self._refresh_library_view)

        self.library_type_filter = QComboBox()
        self.library_type_filter.setObjectName("libraryFilter")
        self.library_type_filter.addItem("Movies + TV", "")
        self.library_type_filter.addItem("Movies", "movie")
        self.library_type_filter.addItem("TV series", "tv")
        self.library_type_filter.currentIndexChanged.connect(self._refresh_library_view)

        self.library_sort_combo = QComboBox()
        self.library_sort_combo.setObjectName("libraryFilter")
        self.library_sort_combo.addItem("Recently updated", "recent")
        self.library_sort_combo.addItem("Highest rated", "rating")
        self.library_sort_combo.addItem("Title A–Z", "title")
        self.library_sort_combo.addItem("Release year", "year")
        self.library_sort_combo.currentIndexChanged.connect(self._refresh_library_view)

        self.library_favourites_filter = QCheckBox("Favourites only")
        self.library_favourites_filter.setObjectName("libraryFavouriteFilter")
        self.library_favourites_filter.stateChanged.connect(self._refresh_library_view)

        filter_row.addWidget(self.library_search_input, 1)
        filter_row.addWidget(self.library_status_filter)
        filter_row.addWidget(self.library_type_filter)
        filter_row.addWidget(self.library_sort_combo)
        filter_row.addWidget(self.library_favourites_filter)
        toolbar_layout.addLayout(filter_row)
        layout.addWidget(toolbar)

        self.library_results_label = QLabel("")
        self.library_results_label.setObjectName("status")
        layout.addWidget(self.library_results_label)

        self.library_scroll = QScrollArea()
        self.library_scroll.setWidgetResizable(True)
        self.library_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.library_grid_widget = QWidget()
        self.library_grid = QGridLayout(self.library_grid_widget)
        self.library_grid.setContentsMargins(2, 2, 8, 8)
        self.library_grid.setHorizontalSpacing(14)
        self.library_grid.setVerticalSpacing(14)
        self.library_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.library_scroll.setWidget(self.library_grid_widget)
        layout.addWidget(self.library_scroll, 1)
        return page

    def _show_search_page(self) -> None:
        self.page_stack.setCurrentWidget(self.search_page)
        self._set_navigation_state("search")

    def _show_library_page(self) -> None:
        self.page_stack.setCurrentWidget(self.library_page)
        self._set_navigation_state("library")
        self._refresh_library_view()

    def _set_navigation_state(self, active: str) -> None:
        buttons = {"search": self.search_nav_button, "library": self.library_nav_button}
        for key, button in buttons.items():
            button.setProperty("active", key == active)
            button.style().unpolish(button)
            button.style().polish(button)

    def _refresh_library_view(self, *_args: object) -> None:
        if not hasattr(self, "library_grid"):
            return

        entries = self.library.list()
        ratings = self.ratings.list()
        totals = rating_totals(ratings)
        status_value = self.library_status_filter.currentData() or None
        type_value = self.library_type_filter.currentData() or None
        sort_value = self.library_sort_combo.currentData() or "recent"
        filtered = prepare_library_entries(
            entries,
            query=self.library_search_input.text(),
            status=status_value,
            media_type=type_value,
            favourite_only=self.library_favourites_filter.isChecked(),
            sort_by=sort_value,
            ratings=totals,
        )

        watched = sum(1 for entry in entries if entry.status == "watched")
        watchlist = sum(1 for entry in entries if entry.status == "watchlist")
        favourites = sum(1 for entry in entries if entry.favourite)
        rated = sum(1 for entry in entries if (entry.media_type, entry.tmdb_id) in totals)
        self.library_summary_label.setText(
            f"{len(entries)} title(s) • {watched} watched • {watchlist} watchlist • "
            f"{favourites} favourite(s) • {rated} rated"
        )
        self.library_results_label.setText(
            f"Showing {len(filtered)} of {len(entries)} saved title(s)."
        )

        self._clear_layout(self.library_grid)
        if not filtered:
            empty = QFrame()
            empty.setObjectName("libraryEmptyState")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(28, 32, 28, 32)
            empty_title = QLabel("Nothing here yet")
            empty_title.setObjectName("sectionTitle")
            empty_text = QLabel(
                "Save titles from Search, or loosen the filters above to see more of your library."
            )
            empty_text.setObjectName("muted")
            empty_text.setWordWrap(True)
            empty_layout.addWidget(empty_title)
            empty_layout.addWidget(empty_text)
            self.library_grid.addWidget(empty, 0, 0, 1, 4)
            self._library_dirty = False
            return

        columns = 4
        for index, entry in enumerate(filtered):
            score = totals.get((entry.media_type, entry.tmdb_id))
            self.library_grid.addWidget(
                self._build_library_card(entry, score),
                index // columns,
                index % columns,
                Qt.AlignmentFlag.AlignTop,
            )
        self._library_dirty = False

    def _build_library_card(
        self,
        entry: MediaLibraryEntry,
        rating_total: float | None,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("libraryCard")
        card.setFixedWidth(220)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(11, 11, 11, 12)
        card_layout.setSpacing(8)

        poster = QLabel("No poster")
        poster.setObjectName("libraryPoster")
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setFixedSize(198, 297)
        card_layout.addWidget(poster, 0, Qt.AlignmentFlag.AlignHCenter)

        url = poster_url(entry.poster_path, "w342")
        if url:
            poster.setText("Loading…")
            self._request_image(
                url,
                lambda pixmap, target=poster: self._set_library_card_poster(target, pixmap),
            )

        title = QLabel(entry.title)
        title.setObjectName("libraryCardTitle")
        title.setWordWrap(True)
        title.setMaximumHeight(44)
        card_layout.addWidget(title)

        meta = QLabel(media_subtitle(entry.media_type, entry.year))
        meta.setObjectName("muted")
        card_layout.addWidget(meta)

        info_row = QHBoxLayout()
        info_row.setSpacing(6)
        status = QLabel(entry.status.title())
        status.setObjectName("libraryStatusBadge")
        info_row.addWidget(status)
        if entry.favourite:
            favourite = QLabel("★ Favourite")
            favourite.setObjectName("libraryFavouriteBadge")
            info_row.addWidget(favourite)
        info_row.addStretch()
        card_layout.addLayout(info_row)

        score = QLabel(
            f"{rating_total:.1f} / 100" if rating_total is not None else "Not rated"
        )
        score.setObjectName("libraryCardRating" if rating_total is not None else "muted")
        card_layout.addWidget(score)

        open_button = QPushButton("Open details")
        open_button.setObjectName("libraryOpenButton")
        open_button.clicked.connect(
            lambda _checked=False, current=entry: self._open_library_entry(current)
        )
        card_layout.addWidget(open_button)
        return card

    def _open_library_entry(self, entry: MediaLibraryEntry) -> None:
        media = MediaSearchResult(
            tmdb_id=entry.tmdb_id,
            media_type=entry.media_type,
            title=entry.title,
            year=entry.year,
            overview=entry.overview,
            poster_path=entry.poster_path,
        )
        self.current_media = media
        self._show_search_page()
        self._show_media_summary(media)
        self._load_library_state(media)
        self._load_rating_state(media)
        self._load_availability(media)

    def _load_saved_services(self) -> None:
        saved = set(self.preferences.get_enabled_services())
        for service_key, checkbox in self.service_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(service_key in saved)
            checkbox.blockSignals(False)

    def _selected_service_keys(self) -> set[str]:
        return {
            key
            for key, checkbox in self.service_checkboxes.items()
            if checkbox.isChecked()
        }

    def _on_service_selection_changed(self, _state: int) -> None:
        selected = self._selected_service_keys()
        self.preferences.set_enabled_services(selected)
        self.status_label.setText("Streaming service preferences saved.")
        if self.current_media is not None:
            self._preference_refresh_timer.start()

    def _start_search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            self.status_label.setText("Enter a movie or TV show first.")
            return

        self.search_button.setEnabled(False)
        self.results_list.clear()
        placeholder = QListWidgetItem("Searching…")
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self.results_list.addItem(placeholder)
        self.status_label.setText(f'Searching TMDB for “{query}”…')
        self._begin_loading()

        worker = AsyncWorker(lambda: self.tmdb.search_media(query))
        worker.signals.result.connect(self._show_search_results)
        worker.signals.error.connect(self._show_error)
        worker.signals.finished.connect(self._finish_search_operation)
        self.thread_pool.start(worker)

    @Slot()
    def _finish_search_operation(self) -> None:
        self.search_button.setEnabled(True)
        self._end_loading()

    def _show_search_results(self, results: object) -> None:
        media_results = list(results) if isinstance(results, list) else []
        self.results_list.clear()

        if not media_results:
            placeholder = QListWidgetItem("No movies or TV shows found.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.results_list.addItem(placeholder)
            self.status_label.setText("No matching titles found.")
            return

        for media in media_results[:30]:
            if not isinstance(media, MediaSearchResult):
                continue
            item = QListWidgetItem(
                f"{media.title}\n{media_subtitle(media.media_type, media.year)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, media.model_dump())
            item.setSizeHint(QSize(0, 112))
            self.results_list.addItem(item)

            url = poster_url(media.poster_path, "w185")
            if url:
                self._request_image(
                    url,
                    lambda pixmap, target=item: self._set_result_poster(target, pixmap),
                )

        self.status_label.setText(f"Found {len(media_results)} result(s).")

    def _on_result_selected(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            return

        self.current_media = MediaSearchResult.model_validate(payload)
        self._show_media_summary(self.current_media)
        self._load_library_state(self.current_media)
        self._load_rating_state(self.current_media)
        self._load_availability(self.current_media)

    def _load_library_state(self, media: MediaSearchResult) -> None:
        entry = self.library.get(media.media_type, media.tmdb_id)
        status_value = entry.status if entry is not None else ""

        self.library_status_combo.blockSignals(True)
        index = self.library_status_combo.findData(status_value)
        self.library_status_combo.setCurrentIndex(max(index, 0))
        self.library_status_combo.setEnabled(True)
        self.library_status_combo.blockSignals(False)

        self.favourite_checkbox.blockSignals(True)
        self.favourite_checkbox.setChecked(bool(entry and entry.favourite))
        self.favourite_checkbox.setEnabled(entry is not None)
        self.favourite_checkbox.blockSignals(False)

    def _load_rating_state(self, media: MediaSearchResult) -> None:
        rating = self.ratings.get(media.media_type, media.tmdb_id)
        self.rate_button.setEnabled(True)
        if rating is None:
            self.rating_summary_label.setText("Not rated")
            self.rate_button.setText("Rate")
            self.rating_summary_label.setToolTip("")
            return

        self.rating_summary_label.setText(f"{rating.total:.1f} / 100")
        self.rate_button.setText("Edit rating")
        breakdown = "\n".join(
            f"{category.label}: {category.score:.1f}/10" for category in rating.categories
        )
        if rating.notes:
            breakdown += f"\n\nNotes: {rating.notes}"
        self.rating_summary_label.setToolTip(breakdown)

    def _open_rating_dialog(self) -> None:
        if self.current_media is None:
            return

        existing: MediaRating | None = self.ratings.get(
            self.current_media.media_type,
            self.current_media.tmdb_id,
        )
        dialog = RatingDialog(self.current_media.title, existing, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        rating = self.ratings.upsert(
            self.current_media.media_type,
            self.current_media.tmdb_id,
            dialog.scores(),
            notes=dialog.notes(),
        )
        self._load_rating_state(self.current_media)
        self._library_dirty = True
        self.status_label.setText(
            f"Saved rating for {self.current_media.title}: {rating.total:.1f}/100."
        )

    def _on_library_status_changed(self, _index: int) -> None:
        if self.current_media is None:
            return

        raw_status = self.library_status_combo.currentData()
        if not raw_status:
            self.library.remove(self.current_media.media_type, self.current_media.tmdb_id)
            self.favourite_checkbox.blockSignals(True)
            self.favourite_checkbox.setChecked(False)
            self.favourite_checkbox.setEnabled(False)
            self.favourite_checkbox.blockSignals(False)
            self._library_dirty = True
            self.status_label.setText(f"Removed {self.current_media.title} from your library.")
            return

        status: LibraryStatus = raw_status
        entry = self.library.upsert(self.current_media, status)
        self.favourite_checkbox.blockSignals(True)
        self.favourite_checkbox.setChecked(entry.favourite)
        self.favourite_checkbox.setEnabled(True)
        self.favourite_checkbox.blockSignals(False)
        self._library_dirty = True
        label = self.library_status_combo.currentText().lower()
        self.status_label.setText(f"Saved {self.current_media.title} as {label}.")

    def _on_favourite_changed(self, state: int) -> None:
        if self.current_media is None:
            return
        raw_status = self.library_status_combo.currentData()
        if not raw_status:
            return

        favourite = state == Qt.CheckState.Checked.value
        self.library.set_favourite(
            self.current_media.media_type,
            self.current_media.tmdb_id,
            favourite,
        )
        self._library_dirty = True
        action = "Added to" if favourite else "Removed from"
        self.status_label.setText(f"{action} favourites: {self.current_media.title}.")

    def _show_media_summary(self, media: MediaSearchResult) -> None:
        self.media_title_label.setText(media.title)
        self.media_meta_label.setText(media_subtitle(media.media_type, media.year))
        self.media_overview_label.setText(media.overview or "No overview available.")
        self.poster_label.clear()
        self.poster_label.setText("Loading poster…" if media.poster_path else "No poster")

        url = poster_url(media.poster_path, "w342")
        if url:
            expected_id = media.tmdb_id
            self._request_image(
                url,
                lambda pixmap, media_id=expected_id: self._set_detail_poster_if_current(
                    media_id, pixmap
                ),
            )

    def _refresh_current_availability(self) -> None:
        if self.current_media is not None:
            self._load_availability(self.current_media)

    def _load_availability(self, media: MediaSearchResult) -> None:
        service_keys = self._selected_service_keys()
        if not service_keys:
            self._set_provider_message(
                "Select at least one streaming service above to check availability."
            )
            self.status_label.setText("No streaming services selected.")
            return

        self._set_provider_message("Checking availability…")
        self.status_label.setText(f"Checking where {media.title} is available…")
        expected_id = media.tmdb_id
        self._availability_generation += 1
        generation = self._availability_generation
        self._begin_loading()

        async def fetch_availability() -> tuple[int, int, MediaAvailability]:
            result = await self.tmdb.get_subscription_availability(
                media.media_type,
                media.tmdb_id,
                service_keys=service_keys,
            )
            return expected_id, generation, result

        worker = AsyncWorker(fetch_availability)
        worker.signals.result.connect(self._handle_availability_result)
        worker.signals.error.connect(self._show_availability_error)
        worker.signals.finished.connect(self._end_loading)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_availability_result(self, payload: object) -> None:
        if (
            not isinstance(payload, tuple)
            or len(payload) != 3
            or not isinstance(payload[0], int)
            or not isinstance(payload[1], int)
        ):
            self._show_availability_error("Unexpected availability worker response.")
            return

        media_id, generation, result = payload
        self._show_availability_if_current(media_id, generation, result)

    @Slot(str)
    def _show_availability_error(self, message: str) -> None:
        self._set_provider_message(
            "Could not load streaming availability. "
            "Check the status message above for details."
        )
        self.status_label.setText(f"Availability error: {message}")

    def _show_availability_if_current(
        self,
        media_id: int,
        generation: int,
        result: object,
    ) -> None:
        if (
            self.current_media is None
            or self.current_media.tmdb_id != media_id
            or generation != self._availability_generation
        ):
            return
        if not isinstance(result, MediaAvailability):
            self._show_error("Unexpected availability response.")
            return

        self.media_title_label.setText(result.title)
        self.media_meta_label.setText(media_subtitle(result.media_type, result.year))
        self.media_overview_label.setText(result.overview or "No overview available.")
        self._clear_layout(self.providers_layout)

        if not result.providers:
            self._set_provider_message(
                "Not currently reported on any of your selected streaming services."
            )
            self.status_label.setText("No matches on your selected services.")
            return

        for provider in result.providers:
            self.providers_layout.addWidget(self._build_provider_card(provider))

        self.status_label.setText(
            f"Found {len(result.providers)} selected service(s) carrying {result.title}."
        )

    def _build_provider_card(self, provider: StreamingServiceAvailability) -> QFrame:
        card = QFrame()
        card.setObjectName("providerCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        logo = QLabel(provider.service_name[:1])
        logo.setObjectName("providerLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(42, 42)
        header.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        name_column = QVBoxLayout()
        name_column.setSpacing(2)
        name = QLabel(provider.service_name)
        name.setObjectName("providerName")
        country_count = QLabel(
            f"{len(provider.countries)} countr{'y' if len(provider.countries) == 1 else 'ies'}"
        )
        country_count.setObjectName("muted")
        name_column.addWidget(name)
        name_column.addWidget(country_count)
        header.addLayout(name_column)
        header.addStretch()
        card_layout.addLayout(header)

        logo_url = provider_logo_url(provider.logo_path, "w92")
        if logo_url:
            self._request_image(
                logo_url,
                lambda pixmap, target=logo: self._set_provider_logo(target, pixmap),
            )

        preview, remainder = split_country_preview(provider.countries, limit=9)
        country_grid = QGridLayout()
        country_grid.setHorizontalSpacing(8)
        country_grid.setVerticalSpacing(7)
        country_grid.setContentsMargins(0, 0, 0, 0)

        chips: list[QLabel] = []
        for index, country in enumerate(preview + remainder):
            chip = QLabel(country.name)
            chip.setObjectName("countryChip")
            chip.setToolTip(country.code)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            if index >= len(preview):
                chip.hide()
            country_grid.addWidget(chip, index // 3, index % 3)
            chips.append(chip)

        card_layout.addLayout(country_grid)

        if remainder:
            more_button = QPushButton(f"+ {len(remainder)} more countries")
            more_button.setObjectName("countryMoreButton")
            more_button.setProperty("remaining_count", len(remainder))
            more_button.clicked.connect(
                lambda _checked=False, hidden=chips[len(preview) :], button=more_button: (
                    self._toggle_country_chips(hidden, button)
                )
            )
            card_layout.addWidget(more_button, 0, Qt.AlignmentFlag.AlignLeft)

        return card

    @staticmethod
    def _toggle_country_chips(chips: list[QLabel], button: QPushButton) -> None:
        if not chips:
            return
        should_show = not chips[0].isVisible()
        for chip in chips:
            chip.setVisible(should_show)
        remaining_count = int(button.property("remaining_count") or len(chips))
        button.setText(
            "Show fewer countries"
            if should_show
            else f"+ {remaining_count} more countries"
        )

    def _set_provider_message(self, message: str) -> None:
        self._clear_layout(self.providers_layout)
        frame = QFrame()
        frame.setObjectName("emptyState")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(14, 12, 14, 12)
        label = QLabel(message)
        label.setObjectName("muted")
        label.setWordWrap(True)
        frame_layout.addWidget(label)
        self.providers_layout.addWidget(frame)

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self.status_label.setText(f"Error: {message}")

    def _begin_loading(self) -> None:
        self._active_operations += 1
        self.loading_bar.show()

    @Slot()
    def _end_loading(self) -> None:
        self._active_operations = max(0, self._active_operations - 1)
        if self._active_operations == 0:
            self.loading_bar.hide()

    def _request_image(
        self,
        url: str,
        callback: Callable[[QPixmap], None],
    ) -> None:
        reply = self.network.get(QNetworkRequest(QUrl(url)))
        reply.finished.connect(
            lambda current_reply=reply, current_callback=callback: self._finish_image_request(
                current_reply,
                current_callback,
            )
        )

    def _finish_image_request(
        self,
        reply: QNetworkReply,
        callback: Callable[[QPixmap], None],
    ) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            pixmap = QPixmap()
            if pixmap.loadFromData(reply.readAll()):
                callback(pixmap)
        finally:
            reply.deleteLater()

    def _set_result_poster(self, item: QListWidgetItem, pixmap: QPixmap) -> None:
        try:
            scaled = pixmap.scaled(
                64,
                96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            item.setIcon(QIcon(scaled))
        except RuntimeError:
            return

    def _set_detail_poster_if_current(self, media_id: int, pixmap: QPixmap) -> None:
        if self.current_media is None or self.current_media.tmdb_id != media_id:
            return
        scaled = pixmap.scaled(
            self.poster_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.poster_label.setText("")
        self.poster_label.setPixmap(scaled)

    @staticmethod
    def _set_library_card_poster(label: QLabel, pixmap: QPixmap) -> None:
        try:
            scaled = pixmap.scaled(
                label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            label.setText("")
            label.setPixmap(scaled)
        except RuntimeError:
            return

    @staticmethod
    def _set_provider_logo(label: QLabel, pixmap: QPixmap) -> None:
        try:
            scaled = pixmap.scaled(
                36,
                36,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            label.setText("")
            label.setPixmap(scaled)
        except RuntimeError:
            return

    @staticmethod
    def _clear_layout(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
