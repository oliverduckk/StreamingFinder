from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer, QUrl, Slot
from PySide6.QtGui import QIcon, QPixmap, QResizeEvent
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
    responsive_column_count,
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
    MetadataAffinitySignal,
    MetadataTasteProfile,
    RatedTitleSummary,
    RatingsDashboard,
    RecommendationItem,
    RecommendationResponse,
    TasteProfile,
    StreamingServiceAvailability,
)
from app.repositories.dismissals import RecommendationDismissalRepository
from app.repositories.features import MediaFeatureRepository
from app.repositories.library import MediaLibraryRepository
from app.repositories.preferences import StreamingPreferencesRepository
from app.repositories.ratings import MediaRatingRepository
from app.services.library_catalog import prepare_library_entries, rating_totals
from app.services.library_classification import LibraryClassificationService
from app.services.media_metadata import MediaMetadataService
from app.services.metadata_taste import build_metadata_taste_profile
from app.services.ratings_dashboard import build_ratings_dashboard
from app.services.recommendations import RecommendationService
from app.services.taste_profile import build_taste_profile
from app.services.streaming_services import STREAMING_SERVICES


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings()
        self.tmdb = TMDBClient(self.settings)
        database = SQLiteDatabase(self.settings.database_path)
        self.preferences = StreamingPreferencesRepository(database)
        self.library = MediaLibraryRepository(database)
        self.library_classifier = LibraryClassificationService(self.tmdb, self.library)
        self.ratings = MediaRatingRepository(database)
        self.dismissals = RecommendationDismissalRepository(database)
        self.features = MediaFeatureRepository(database)
        self.metadata = MediaMetadataService(self.tmdb, self.features)
        self.recommendations = RecommendationService(
            self.tmdb,
            self.library,
            self.ratings,
            self.preferences,
            self.dismissals,
            metadata=self.metadata,
        )
        self.thread_pool = QThreadPool.globalInstance()
        self.network = QNetworkAccessManager(self)
        self.current_media: MediaSearchResult | None = None
        self.service_checkboxes: dict[str, QCheckBox] = {}
        self._availability_generation = 0
        self._active_operations = 0
        self._library_dirty = True
        self._library_classification_running = False
        self._ratings_dirty = True
        self._metadata_profile_running = False
        self._recommendations_dirty = True
        self._library_cards: list[QWidget] = []
        self._recommendation_cards: list[QWidget] = []
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
        self.ratings_nav_button = QPushButton("Ratings")
        self.ratings_nav_button.setObjectName("navButton")
        self.ratings_nav_button.clicked.connect(self._show_ratings_page)
        self.recommendations_nav_button = QPushButton("Recommendations")
        self.recommendations_nav_button.setObjectName("navButton")
        self.recommendations_nav_button.clicked.connect(self._show_recommendations_page)
        navigation.addWidget(self.search_nav_button)
        navigation.addWidget(self.library_nav_button)
        navigation.addWidget(self.ratings_nav_button)
        navigation.addWidget(self.recommendations_nav_button)
        navigation.addStretch()
        root_layout.addLayout(navigation)

        self.page_stack = QStackedWidget()
        self.search_page = self._build_search_page()
        self.library_page = self._build_library_page()
        self.ratings_page = self._build_ratings_page()
        self.recommendations_page = self._build_recommendations_page()
        self.page_stack.addWidget(self.search_page)
        self.page_stack.addWidget(self.library_page)
        self.page_stack.addWidget(self.ratings_page)
        self.page_stack.addWidget(self.recommendations_page)
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
        self.library_type_filter.addItem("Everything", "all")
        self.library_type_filter.addItem("Movies", "movie")
        self.library_type_filter.addItem("TV series (live action)", "tv")
        self.library_type_filter.addItem("Anime", "anime")
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
        self.library_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.library_scroll.setWidget(self.library_grid_widget)
        layout.addWidget(self.library_scroll, 1)
        return page

    def _build_ratings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("panel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_text = QVBoxLayout()
        heading = QLabel("Ratings dashboard")
        heading.setObjectName("ratingsHeading")
        self.ratings_summary_label = QLabel(
            "Your rating history will turn into a taste profile here."
        )
        self.ratings_summary_label.setObjectName("muted")
        header_text.addWidget(heading)
        header_text.addWidget(self.ratings_summary_label)
        header_layout.addLayout(header_text)
        header_layout.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.ratings_content_layout = QVBoxLayout(content)
        self.ratings_content_layout.setContentsMargins(0, 0, 8, 8)
        self.ratings_content_layout.setSpacing(14)

        self.ratings_empty_state = QFrame()
        self.ratings_empty_state.setObjectName("ratingsEmptyState")
        empty_layout = QVBoxLayout(self.ratings_empty_state)
        empty_layout.setContentsMargins(28, 34, 28, 34)
        empty_title = QLabel("No ratings yet")
        empty_title.setObjectName("sectionTitle")
        empty_text = QLabel(
            "Rate a movie or show from Search and your averages, rankings, "
            "and category profile will appear here."
        )
        empty_text.setObjectName("muted")
        empty_text.setWordWrap(True)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_text)
        self.ratings_content_layout.addWidget(self.ratings_empty_state)

        self.ratings_dashboard_container = QWidget()
        dashboard_layout = QVBoxLayout(self.ratings_dashboard_container)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(14)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.rated_count_value = QLabel("0")
        self.average_rating_value = QLabel("—")
        self.movie_average_value = QLabel("—")
        self.tv_average_value = QLabel("—")
        metrics.addWidget(self._build_rating_stat_card("Rated titles", self.rated_count_value))
        metrics.addWidget(self._build_rating_stat_card("Average score", self.average_rating_value))
        metrics.addWidget(self._build_rating_stat_card("Movie average", self.movie_average_value))
        metrics.addWidget(self._build_rating_stat_card("TV average", self.tv_average_value))
        dashboard_layout.addLayout(metrics)

        taste_panel = QFrame()
        taste_panel.setObjectName("tasteProfilePanel")
        taste_layout = QVBoxLayout(taste_panel)
        taste_layout.setContentsMargins(16, 14, 16, 16)
        taste_layout.setSpacing(10)

        taste_header = QHBoxLayout()
        taste_title = QLabel("Taste profile")
        taste_title.setObjectName("sectionTitle")
        self.taste_confidence_badge = QLabel("EARLY")
        self.taste_confidence_badge.setObjectName("tasteConfidenceBadge")
        taste_header.addWidget(taste_title)
        taste_header.addStretch()
        taste_header.addWidget(self.taste_confidence_badge)
        taste_layout.addLayout(taste_header)

        self.taste_summary_label = QLabel(
            "Rate a few titles and StreamingFinder will start mapping your taste."
        )
        self.taste_summary_label.setObjectName("muted")
        self.taste_summary_label.setWordWrap(True)
        taste_layout.addWidget(self.taste_summary_label)

        taste_columns = QHBoxLayout()
        taste_columns.setSpacing(18)

        strengths_column = QVBoxLayout()
        strengths_heading = QLabel("Highest-scoring traits")
        strengths_heading.setObjectName("tasteSubheading")
        strengths_column.addWidget(strengths_heading)
        self.taste_strengths_layout = QVBoxLayout()
        self.taste_strengths_layout.setSpacing(6)
        strengths_column.addLayout(self.taste_strengths_layout)
        strengths_column.addStretch()
        taste_columns.addLayout(strengths_column, 1)

        alignment_column = QVBoxLayout()
        alignment_heading = QLabel("What moves with Enjoyment")
        alignment_heading.setObjectName("tasteSubheading")
        alignment_column.addWidget(alignment_heading)
        self.taste_alignment_layout = QVBoxLayout()
        self.taste_alignment_layout.setSpacing(6)
        alignment_column.addLayout(self.taste_alignment_layout)
        alignment_column.addStretch()
        taste_columns.addLayout(alignment_column, 1)
        taste_layout.addLayout(taste_columns)

        self.taste_favourite_label = QLabel("")
        self.taste_favourite_label.setObjectName("tasteFootnote")
        self.taste_favourite_label.setWordWrap(True)
        taste_layout.addWidget(self.taste_favourite_label)
        dashboard_layout.addWidget(taste_panel)

        metadata_panel = QFrame()
        metadata_panel.setObjectName("tasteProfilePanel")
        metadata_layout = QVBoxLayout(metadata_panel)
        metadata_layout.setContentsMargins(16, 14, 16, 16)
        metadata_layout.setSpacing(10)

        metadata_header = QHBoxLayout()
        metadata_title = QLabel("Metadata taste model")
        metadata_title.setObjectName("sectionTitle")
        self.metadata_coverage_label = QLabel("Not analysed yet")
        self.metadata_coverage_label.setObjectName("muted")
        self.metadata_confidence_badge = QLabel("EARLY")
        self.metadata_confidence_badge.setObjectName("tasteConfidenceBadge")
        metadata_header.addWidget(metadata_title)
        metadata_header.addWidget(self.metadata_coverage_label)
        metadata_header.addStretch()
        metadata_header.addWidget(self.metadata_confidence_badge)
        metadata_layout.addLayout(metadata_header)

        self.metadata_summary_label = QLabel(
            "Open Ratings and StreamingFinder will map genres, themes and creators "
            "across your rated library."
        )
        self.metadata_summary_label.setObjectName("muted")
        self.metadata_summary_label.setWordWrap(True)
        metadata_layout.addWidget(self.metadata_summary_label)

        metadata_columns = QHBoxLayout()
        metadata_columns.setSpacing(18)

        positive_column = QVBoxLayout()
        positive_heading = QLabel("Leans toward")
        positive_heading.setObjectName("tasteSubheading")
        positive_column.addWidget(positive_heading)
        self.metadata_positive_layout = QVBoxLayout()
        self.metadata_positive_layout.setSpacing(6)
        positive_column.addLayout(self.metadata_positive_layout)
        positive_column.addStretch()
        metadata_columns.addLayout(positive_column, 1)

        negative_column = QVBoxLayout()
        negative_heading = QLabel("Leans away from")
        negative_heading.setObjectName("tasteSubheading")
        negative_column.addWidget(negative_heading)
        self.metadata_negative_layout = QVBoxLayout()
        self.metadata_negative_layout.setSpacing(6)
        negative_column.addLayout(self.metadata_negative_layout)
        negative_column.addStretch()
        metadata_columns.addLayout(negative_column, 1)

        metadata_layout.addLayout(metadata_columns)
        dashboard_layout.addWidget(metadata_panel)

        split = QHBoxLayout()
        split.setSpacing(14)

        category_panel = QFrame()
        category_panel.setObjectName("panel")
        category_layout = QVBoxLayout(category_panel)
        category_layout.setContentsMargins(16, 14, 16, 16)
        category_layout.setSpacing(9)
        category_title = QLabel("Category averages")
        category_title.setObjectName("sectionTitle")
        category_layout.addWidget(category_title)
        category_hint = QLabel("Your average score out of 10 for each rating category.")
        category_hint.setObjectName("muted")
        category_hint.setWordWrap(True)
        category_layout.addWidget(category_hint)
        self.category_average_layout = QVBoxLayout()
        self.category_average_layout.setSpacing(8)
        category_layout.addLayout(self.category_average_layout)
        category_layout.addStretch()
        split.addWidget(category_panel, 1)

        top_panel = QFrame()
        top_panel.setObjectName("panel")
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(16, 14, 16, 16)
        top_layout.setSpacing(9)
        top_title = QLabel("Highest rated")
        top_title.setObjectName("sectionTitle")
        top_layout.addWidget(top_title)
        top_hint = QLabel("Your current top-rated movies and shows.")
        top_hint.setObjectName("muted")
        top_layout.addWidget(top_hint)
        self.top_rated_layout = QVBoxLayout()
        self.top_rated_layout.setSpacing(8)
        top_layout.addLayout(self.top_rated_layout)
        top_layout.addStretch()
        split.addWidget(top_panel, 1)
        dashboard_layout.addLayout(split)

        recent_panel = QFrame()
        recent_panel.setObjectName("panel")
        recent_layout = QVBoxLayout(recent_panel)
        recent_layout.setContentsMargins(16, 14, 16, 16)
        recent_layout.setSpacing(9)
        recent_title = QLabel("Recently rated")
        recent_title.setObjectName("sectionTitle")
        recent_layout.addWidget(recent_title)
        self.recent_rated_layout = QVBoxLayout()
        self.recent_rated_layout.setSpacing(8)
        recent_layout.addLayout(self.recent_rated_layout)
        dashboard_layout.addWidget(recent_panel)

        self.ratings_content_layout.addWidget(self.ratings_dashboard_container)
        self.ratings_content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.ratings_dashboard_container.hide()
        return page

    def _build_recommendations_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("recommendationsHero")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 15, 18, 15)
        header_layout.setSpacing(14)

        text_column = QVBoxLayout()
        text_column.setSpacing(4)
        heading = QLabel("What should I watch?")
        heading.setObjectName("recommendationsHeading")
        description = QLabel(
            "Blends your high and low ratings with genres, keywords and creators, "
            "then diversifies the results and checks worldwide availability."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        text_column.addWidget(heading)
        text_column.addWidget(description)
        header_layout.addLayout(text_column, 1)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.recommendation_type_combo = QComboBox()
        self.recommendation_type_combo.addItem("Movies + TV", "all")
        self.recommendation_type_combo.addItem("Movies", "movie")
        self.recommendation_type_combo.addItem("TV series (live action)", "tv")
        self.recommendation_type_combo.addItem("Anime (movies + series)", "anime")
        self.recommendation_type_combo.addItem("Anime series", "anime_tv")
        self.recommendation_type_combo.addItem("Anime movies", "anime_movie")
        controls.addWidget(self.recommendation_type_combo)

        self.recommendation_discovery_combo = QComboBox()
        self.recommendation_discovery_combo.setToolTip(
            "Familiar favours well-known titles; Hidden gems allows much smaller TMDB audiences."
        )
        self.recommendation_discovery_combo.addItem("Familiar", "familiar")
        self.recommendation_discovery_combo.addItem("Balanced", "balanced")
        self.recommendation_discovery_combo.addItem("Hidden gems", "hidden")
        controls.addWidget(self.recommendation_discovery_combo)

        self.recommendation_services_checkbox = QCheckBox("Only my services")
        self.recommendation_services_checkbox.setChecked(True)
        controls.addWidget(self.recommendation_services_checkbox)

        self.recommendation_refresh_button = QPushButton("Recommend something")
        self.recommendation_refresh_button.setProperty("accent", True)
        self.recommendation_refresh_button.clicked.connect(self._refresh_recommendations)
        controls.addWidget(self.recommendation_refresh_button)
        header_layout.addLayout(controls)
        layout.addWidget(header)

        self.recommendation_status_label = QLabel(
            "Generate a fresh set whenever you want something new to watch."
        )
        self.recommendation_status_label.setObjectName("status")
        self.recommendation_status_label.setWordWrap(True)
        layout.addWidget(self.recommendation_status_label)

        self.recommendation_loading_bar = QProgressBar()
        self.recommendation_loading_bar.setObjectName("loadingBar")
        self.recommendation_loading_bar.setRange(0, 0)
        self.recommendation_loading_bar.setTextVisible(False)
        self.recommendation_loading_bar.setFixedHeight(3)
        self.recommendation_loading_bar.hide()
        layout.addWidget(self.recommendation_loading_bar)

        self.recommendation_scroll = QScrollArea()
        self.recommendation_scroll.setWidgetResizable(True)
        self.recommendation_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        self.recommendations_grid = QGridLayout(content)
        self.recommendations_grid.setContentsMargins(2, 2, 8, 8)
        self.recommendations_grid.setHorizontalSpacing(14)
        self.recommendations_grid.setVerticalSpacing(14)
        self.recommendations_grid.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        self.recommendation_scroll.setWidget(content)
        layout.addWidget(self.recommendation_scroll, 1)

        self._set_recommendations_message(
            "Your rating history powers this page. Hit Recommend something when you're ready."
        )
        return page

    @staticmethod
    def _build_rating_stat_card(label_text: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("ratingStatCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 13, 16, 13)
        card_layout.setSpacing(4)
        value_label.setObjectName("ratingStatValue")
        label = QLabel(label_text)
        label.setObjectName("ratingStatLabel")
        card_layout.addWidget(value_label)
        card_layout.addWidget(label)
        return card

    def _show_search_page(self) -> None:
        self.page_stack.setCurrentWidget(self.search_page)
        self._set_navigation_state("search")

    def _show_library_page(self) -> None:
        self.page_stack.setCurrentWidget(self.library_page)
        self._set_navigation_state("library")
        self._refresh_library_view()
        self._backfill_library_classifications()

    def _show_ratings_page(self) -> None:
        self.page_stack.setCurrentWidget(self.ratings_page)
        self._set_navigation_state("ratings")
        self._refresh_ratings_dashboard()

    def _show_recommendations_page(self) -> None:
        self.page_stack.setCurrentWidget(self.recommendations_page)
        self._set_navigation_state("recommendations")
        if self._recommendations_dirty:
            self._set_recommendations_message(
                "Your ratings or library changed. Generate a fresh set to update recommendations."
            )

    def _set_navigation_state(self, active: str) -> None:
        buttons = {
            "search": self.search_nav_button,
            "library": self.library_nav_button,
            "ratings": self.ratings_nav_button,
            "recommendations": self.recommendations_nav_button,
        }
        for key, button in buttons.items():
            button.setProperty("active", key == active)
            button.style().unpolish(button)
            button.style().polish(button)

    def _refresh_recommendations(self) -> None:
        media_type = self.recommendation_type_combo.currentData() or "all"
        discovery_mode = self.recommendation_discovery_combo.currentData() or "familiar"
        only_my_services = self.recommendation_services_checkbox.isChecked()
        self.recommendation_refresh_button.setEnabled(False)
        self.recommendation_loading_bar.show()
        self.recommendation_status_label.setText(
            "Building your taste model, diversifying candidates and checking availability…"
            if only_my_services
            else "Building your taste model and diversifying candidates…"
        )
        self._set_recommendations_message("Finding a fresh set…")

        async def fetch() -> RecommendationResponse:
            return await self.recommendations.recommend(
                media_type=media_type,
                limit=12,
                only_my_services=only_my_services,
                discovery_mode=discovery_mode,
            )

        worker = AsyncWorker(fetch)
        worker.signals.result.connect(self._handle_recommendations_result)
        worker.signals.error.connect(self._show_recommendations_error)
        worker.signals.finished.connect(self._finish_recommendations_loading)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_recommendations_result(self, payload: object) -> None:
        if not isinstance(payload, RecommendationResponse):
            self._show_recommendations_error("Unexpected recommendation response.")
            return
        self.recommendation_status_label.setText(payload.message)
        self._clear_layout(self.recommendations_grid)
        self._recommendation_cards = []
        if not payload.items:
            self._set_recommendations_message(payload.message)
            self._recommendations_dirty = False
            return

        self._recommendation_cards = [
            self._build_recommendation_card(item) for item in payload.items
        ]
        self._reflow_recommendations_grid()
        self._recommendations_dirty = False

    @Slot(str)
    def _show_recommendations_error(self, message: str) -> None:
        self.recommendation_status_label.setText(f"Recommendation error: {message}")
        self._set_recommendations_message(
            "Could not generate recommendations. Check your TMDB connection and try again."
        )

    @Slot()
    def _finish_recommendations_loading(self) -> None:
        self.recommendation_loading_bar.hide()
        self.recommendation_refresh_button.setEnabled(True)

    def _set_recommendations_message(self, message: str) -> None:
        if not hasattr(self, "recommendations_grid"):
            return
        self._clear_layout(self.recommendations_grid)
        self._recommendation_cards = []
        frame = QFrame()
        frame.setObjectName("recommendationsEmptyState")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(28, 34, 28, 34)
        title = QLabel("Personal recommendations")
        title.setObjectName("sectionTitle")
        body = QLabel(message)
        body.setObjectName("muted")
        body.setWordWrap(True)
        frame_layout.addWidget(title)
        frame_layout.addWidget(body)
        self.recommendations_grid.addWidget(frame, 0, 0, 1, 1)

    def _build_recommendation_card(self, item: RecommendationItem) -> QFrame:
        card = QFrame()
        card.setObjectName("recommendationCard")
        card.setFixedWidth(350)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 13)
        card_layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(11)
        poster = QLabel("No poster")
        poster.setObjectName("recommendationPoster")
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setFixedSize(112, 168)
        top.addWidget(poster, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(5)
        score = QLabel(f"Match {item.match_score:.1f} / 100")
        score.setObjectName("recommendationScore")
        info.addWidget(score)
        title = QLabel(item.title)
        title.setObjectName("recommendationTitle")
        title.setWordWrap(True)
        info.addWidget(title)
        meta = QLabel(media_subtitle(item.media_type, item.year))
        meta.setObjectName("muted")
        info.addWidget(meta)
        if item.genre_names:
            genres = QLabel(" • ".join(item.genre_names[:3]))
            genres.setObjectName("recommendationAudience")
            genres.setWordWrap(True)
            info.addWidget(genres)
        if item.tmdb_vote_count:
            audience = QLabel(
                f"TMDB {item.tmdb_vote_average:.1f}/10 • {item.tmdb_vote_count:,} votes"
            )
            audience.setObjectName("recommendationAudience")
            audience.setWordWrap(True)
            info.addWidget(audience)
        if item.on_watchlist:
            watchlist_badge = QLabel("ON YOUR WATCHLIST")
            watchlist_badge.setObjectName("recommendationWatchlistBadge")
            info.addWidget(watchlist_badge, 0, Qt.AlignmentFlag.AlignLeft)
        info.addStretch()
        top.addLayout(info, 1)
        card_layout.addLayout(top)

        url = poster_url(item.poster_path, "w342")
        if url:
            self._request_image(
                url,
                lambda pixmap, target=poster: self._set_library_card_poster(target, pixmap),
            )

        reason_heading = QLabel("Why this fits")
        reason_heading.setObjectName("recommendationSubheading")
        card_layout.addWidget(reason_heading)
        for reason in item.reasons[:2]:
            label = QLabel(f"• {reason}")
            label.setObjectName("recommendationReason")
            label.setWordWrap(True)
            card_layout.addWidget(label)

        if item.providers:
            availability_heading = QLabel("Where you can stream it")
            availability_heading.setObjectName("recommendationSubheading")
            card_layout.addWidget(availability_heading)
            for provider in item.providers[:2]:
                names = [country.name for country in provider.countries[:3]]
                extra = len(provider.countries) - len(names)
                countries = ", ".join(names)
                if extra > 0:
                    countries += f" +{extra}"
                line = QLabel(f"{provider.service_name}: {countries or 'Available'}")
                line.setObjectName("recommendationAvailability")
                line.setWordWrap(True)
                card_layout.addWidget(line)

        primary_actions = QHBoxLayout()
        open_button = QPushButton("Open details")
        open_button.setObjectName("recommendationOpenButton")
        open_button.clicked.connect(
            lambda _checked=False, current=item: self._open_recommendation(current)
        )
        primary_actions.addWidget(open_button)

        watchlist_button = QPushButton(
            "On watchlist" if item.on_watchlist else "Add to watchlist"
        )
        watchlist_button.setObjectName("recommendationWatchlistButton")
        watchlist_button.setEnabled(not item.on_watchlist)
        watchlist_button.clicked.connect(
            lambda _checked=False, current=item, button=watchlist_button: (
                self._add_recommendation_to_watchlist(current, button)
            )
        )
        primary_actions.addWidget(watchlist_button)
        card_layout.addLayout(primary_actions)

        feedback_actions = QHBoxLayout()
        watched_button = QPushButton("I've watched this")
        watched_button.setObjectName("recommendationFeedbackButton")
        watched_button.clicked.connect(
            lambda _checked=False, current=item, target=card: (
                self._mark_recommendation_watched(current, target)
            )
        )
        feedback_actions.addWidget(watched_button)

        dismiss_button = QPushButton("Not interested")
        dismiss_button.setObjectName("recommendationFeedbackButton")
        dismiss_button.clicked.connect(
            lambda _checked=False, current=item, target=card: (
                self._dismiss_recommendation(current, target)
            )
        )
        feedback_actions.addWidget(dismiss_button)
        card_layout.addLayout(feedback_actions)
        return card

    def _open_recommendation(self, item: RecommendationItem) -> None:
        media = MediaSearchResult(
            tmdb_id=item.tmdb_id,
            media_type=item.media_type,
            title=item.title,
            year=item.year,
            overview=item.overview,
            poster_path=item.poster_path,
            is_anime=item.is_anime,
        )
        self.current_media = media
        self._show_search_page()
        self._show_media_summary(media)
        self._load_library_state(media)
        self._load_rating_state(media)
        self._load_availability(media)

    def _add_recommendation_to_watchlist(
        self,
        item: RecommendationItem,
        button: QPushButton,
    ) -> None:
        media = MediaSearchResult(
            tmdb_id=item.tmdb_id,
            media_type=item.media_type,
            title=item.title,
            year=item.year,
            overview=item.overview,
            poster_path=item.poster_path,
            is_anime=item.is_anime,
        )
        self.library.upsert(media, "watchlist")
        item.on_watchlist = True
        button.setText("On watchlist")
        button.setEnabled(False)
        self._library_dirty = True
        self._recommendations_dirty = True
        self.recommendation_status_label.setText(f"Added {item.title} to your watchlist.")

    def _mark_recommendation_watched(
        self,
        item: RecommendationItem,
        card: QWidget,
    ) -> None:
        media = MediaSearchResult(
            tmdb_id=item.tmdb_id,
            media_type=item.media_type,
            title=item.title,
            year=item.year,
            overview=item.overview,
            poster_path=item.poster_path,
            is_anime=item.is_anime,
        )
        self.library.upsert(media, "watched")
        self._library_dirty = True
        self._ratings_dirty = True
        self._recommendations_dirty = True
        self.recommendation_status_label.setText(
            f"Marked {item.title} as watched. It will be excluded from future recommendations."
        )
        self._remove_recommendation_card(card)

    def _dismiss_recommendation(
        self,
        item: RecommendationItem,
        card: QWidget,
    ) -> None:
        self.dismissals.add(item.media_type, item.tmdb_id, item.title)
        self._recommendations_dirty = True
        self.recommendation_status_label.setText(
            f"Hidden {item.title} from future recommendations."
        )
        self._remove_recommendation_card(card)

    def _remove_recommendation_card(self, card: QWidget) -> None:
        if card in self._recommendation_cards:
            self._recommendation_cards.remove(card)
        self.recommendations_grid.removeWidget(card)
        card.deleteLater()
        QTimer.singleShot(0, self._reflow_recommendations_grid)

    def _refresh_ratings_dashboard(self) -> None:
        if not hasattr(self, "ratings_dashboard_container"):
            return

        ratings = self.ratings.list()
        library_entries = self.library.list()
        dashboard = build_ratings_dashboard(ratings, library_entries)
        taste_profile = build_taste_profile(ratings, library_entries)
        self.ratings_summary_label.setText(self._ratings_summary_text(dashboard))
        self._refresh_taste_profile(taste_profile)

        if dashboard.total_rated == 0:
            self._reset_metadata_profile()
        else:
            self._start_metadata_profile_refresh(ratings, library_entries)

        if dashboard.total_rated == 0:
            self.ratings_empty_state.show()
            self.ratings_dashboard_container.hide()
            self._ratings_dirty = False
            return

        self.ratings_empty_state.hide()
        self.ratings_dashboard_container.show()
        self.rated_count_value.setText(str(dashboard.total_rated))
        self.average_rating_value.setText(self._format_score(dashboard.average_total))
        self.movie_average_value.setText(self._format_score(dashboard.movie_average))
        self.tv_average_value.setText(self._format_score(dashboard.tv_average))

        self._clear_layout(self.category_average_layout)
        for category in dashboard.category_averages:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(9)
            label = QLabel(category.label)
            label.setFixedWidth(125)
            bar = QProgressBar()
            bar.setObjectName("ratingCategoryBar")
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(9)
            if category.average is not None:
                bar.setValue(round(category.average * 10))
            value = QLabel(
                f"{category.average:.2f}" if category.average is not None else "—"
            )
            value.setObjectName("ratingCategoryValue")
            value.setFixedWidth(42)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(label)
            row_layout.addWidget(bar, 1)
            row_layout.addWidget(value)
            self.category_average_layout.addWidget(row)

        self._populate_rating_title_list(self.top_rated_layout, dashboard.top_rated)
        self._populate_rating_title_list(self.recent_rated_layout, dashboard.recent_rated)
        self._ratings_dirty = False

    def _refresh_taste_profile(self, profile: TasteProfile) -> None:
        self.taste_confidence_badge.setText(profile.confidence.upper())
        self.taste_confidence_badge.setProperty("confidence", profile.confidence)
        self.taste_confidence_badge.style().unpolish(self.taste_confidence_badge)
        self.taste_confidence_badge.style().polish(self.taste_confidence_badge)
        self.taste_summary_label.setText(profile.summary)

        self._clear_layout(self.taste_strengths_layout)
        if profile.strongest_categories:
            for signal in profile.strongest_categories:
                row = QFrame()
                row.setObjectName("tasteSignalRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 7, 10, 7)
                label = QLabel(signal.label)
                label.setObjectName("tasteSignalLabel")
                row_layout.addWidget(label)
                row_layout.addStretch()
                delta = signal.delta_from_personal_mean
                delta_text = f"{delta:+.2f}" if abs(delta) >= 0.005 else "±0.00"
                value = QLabel(f"{signal.average:.2f}  ({delta_text})")
                value.setObjectName("tasteSignalValue")
                value.setToolTip("Average score and difference from your mean category score.")
                row_layout.addWidget(value)
                self.taste_strengths_layout.addWidget(row)
        else:
            placeholder = QLabel("Rate something first.")
            placeholder.setObjectName("muted")
            self.taste_strengths_layout.addWidget(placeholder)

        self._clear_layout(self.taste_alignment_layout)
        if profile.enjoyment_alignments:
            for signal in profile.enjoyment_alignments:
                row = QFrame()
                row.setObjectName("tasteSignalRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 7, 10, 7)
                text_column = QVBoxLayout()
                text_column.setSpacing(1)
                label = QLabel(signal.label)
                label.setObjectName("tasteSignalLabel")
                detail = QLabel(f"Across {signal.sample_size} rated titles")
                detail.setObjectName("muted")
                text_column.addWidget(label)
                text_column.addWidget(detail)
                row_layout.addLayout(text_column, 1)
                value = QLabel(f"{signal.correlation:+.2f}")
                value.setObjectName("tasteCorrelationValue")
                value.setToolTip(
                    "Pearson correlation with your Enjoyment score. "
                    "This is a pattern in your ratings, not proof of causation."
                )
                row_layout.addWidget(value)
                self.taste_alignment_layout.addWidget(row)
        else:
            placeholder = QLabel(
                "Needs at least 3 ratings with some score variation before a useful pattern appears."
            )
            placeholder.setObjectName("muted")
            placeholder.setWordWrap(True)
            self.taste_alignment_layout.addWidget(placeholder)

        if profile.favourite_delta is None:
            self.taste_favourite_label.setText(
                "Favourite signal will appear once you have rated both favourite and non-favourite titles."
            )
        else:
            sign = "+" if profile.favourite_delta >= 0 else ""
            self.taste_favourite_label.setText(
                f"Your favourites currently average {profile.favourite_average:.1f}/100 versus "
                f"{profile.non_favourite_average:.1f}/100 for other rated titles "
                f"({sign}{profile.favourite_delta:.1f} points)."
            )

    def _start_metadata_profile_refresh(
        self,
        ratings: list[MediaRating],
        library_entries: list[MediaLibraryEntry],
    ) -> None:
        if self._metadata_profile_running:
            return
        self._metadata_profile_running = True
        self.metadata_summary_label.setText(
            f"Analysing genres, themes and creators across {len(ratings)} rated title(s)…"
        )
        self.metadata_coverage_label.setText("Building local metadata cache…")

        async def build_profile() -> MetadataTasteProfile:
            features = await self.metadata.get_many(
                [(rating.media_type, rating.tmdb_id) for rating in ratings]
            )
            return build_metadata_taste_profile(ratings, library_entries, features)

        worker = AsyncWorker(build_profile)
        worker.signals.result.connect(self._handle_metadata_profile_result)
        worker.signals.error.connect(self._handle_metadata_profile_error)
        worker.signals.finished.connect(self._finish_metadata_profile_refresh)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_metadata_profile_result(self, payload: object) -> None:
        if not isinstance(payload, MetadataTasteProfile):
            self._handle_metadata_profile_error("Unexpected metadata profile response.")
            return
        self._refresh_metadata_profile(payload)

    @Slot(str)
    def _handle_metadata_profile_error(self, message: str) -> None:
        self.metadata_summary_label.setText(
            f"Could not finish metadata taste analysis: {message}"
        )
        self.metadata_coverage_label.setText("Analysis unavailable")

    @Slot()
    def _finish_metadata_profile_refresh(self) -> None:
        self._metadata_profile_running = False

    def _reset_metadata_profile(self) -> None:
        self.metadata_confidence_badge.setText("EMPTY")
        self.metadata_coverage_label.setText("No rated titles")
        self.metadata_summary_label.setText(
            "Rate a few titles and StreamingFinder will map genres, themes and creators."
        )
        self._clear_layout(self.metadata_positive_layout)
        self._clear_layout(self.metadata_negative_layout)

    def _refresh_metadata_profile(self, profile: MetadataTasteProfile) -> None:
        self.metadata_confidence_badge.setText(profile.confidence.upper())
        self.metadata_confidence_badge.setProperty("confidence", profile.confidence)
        self.metadata_confidence_badge.style().unpolish(self.metadata_confidence_badge)
        self.metadata_confidence_badge.style().polish(self.metadata_confidence_badge)
        self.metadata_coverage_label.setText(
            f"{profile.metadata_coverage}/{profile.total_rated} rated titles analysed"
        )
        self.metadata_summary_label.setText(profile.summary)
        self._populate_metadata_affinities(
            self.metadata_positive_layout,
            [
                ("Genres", profile.positive_genres),
                ("Themes / keywords", profile.positive_keywords),
                ("Creators / directors", profile.positive_creators),
            ],
            positive=True,
        )
        self._populate_metadata_affinities(
            self.metadata_negative_layout,
            [
                ("Genres", profile.negative_genres),
                ("Themes / keywords", profile.negative_keywords),
                ("Creators / directors", profile.negative_creators),
            ],
            positive=False,
        )

    def _populate_metadata_affinities(
        self,
        layout: QLayout,
        groups: list[tuple[str, list[MetadataAffinitySignal]]],
        *,
        positive: bool,
    ) -> None:
        self._clear_layout(layout)
        added = False
        for heading_text, signals in groups:
            if not signals:
                continue
            heading = QLabel(heading_text)
            heading.setObjectName("muted")
            layout.addWidget(heading)
            for signal in signals[:3]:
                row = QFrame()
                row.setObjectName("tasteSignalRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 7, 10, 7)
                text = QVBoxLayout()
                text.setSpacing(1)
                label = QLabel(signal.label)
                label.setObjectName("tasteSignalLabel")
                evidence = QLabel(
                    f"{signal.sample_size} title(s) • "
                    f"{signal.positive_evidence} positive / {signal.negative_evidence} negative"
                )
                evidence.setObjectName("muted")
                text.addWidget(label)
                text.addWidget(evidence)
                row_layout.addLayout(text, 1)
                value = QLabel(f"{signal.affinity:+.2f}")
                value.setObjectName(
                    "tasteCorrelationValue" if positive else "tasteSignalValue"
                )
                if signal.supporting_titles:
                    value.setToolTip("Strong evidence: " + ", ".join(signal.supporting_titles))
                row_layout.addWidget(value)
                layout.addWidget(row)
                added = True
        if not added:
            placeholder = QLabel(
                "No strong positive metadata pattern yet."
                if positive
                else "No strong negative metadata pattern yet."
            )
            placeholder.setObjectName("muted")
            placeholder.setWordWrap(True)
            layout.addWidget(placeholder)

    @staticmethod
    def _ratings_summary_text(dashboard: RatingsDashboard) -> str:
        if dashboard.total_rated == 0:
            return "Your rating history will turn into a taste profile here."
        average = (
            f"{dashboard.average_total:.1f}/100"
            if dashboard.average_total is not None
            else "—"
        )
        highest = (
            f"{dashboard.highest_total:.1f}/100"
            if dashboard.highest_total is not None
            else "—"
        )
        return (
            f"{dashboard.total_rated} rated title(s) • "
            f"{average} average • {highest} highest"
        )

    @staticmethod
    def _format_score(score: float | None) -> str:
        return f"{score:.1f}" if score is not None else "—"

    def _populate_rating_title_list(
        self,
        layout: QLayout,
        items: list[RatedTitleSummary],
    ) -> None:
        self._clear_layout(layout)
        if not items:
            placeholder = QLabel("No matching ratings yet.")
            placeholder.setObjectName("muted")
            layout.addWidget(placeholder)
            return
        for item in items:
            layout.addWidget(self._build_rating_title_row(item))

    def _build_rating_title_row(self, item: RatedTitleSummary) -> QFrame:
        row = QFrame()
        row.setObjectName("ratingsListRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(11, 9, 11, 9)
        row_layout.setSpacing(10)

        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        title = QLabel(item.title)
        title.setObjectName("ratingsRowTitle")
        title.setWordWrap(True)
        meta_text = media_subtitle(item.media_type, item.year)
        if item.favourite:
            meta_text += " • ★ Favourite"
        meta = QLabel(meta_text)
        meta.setObjectName("muted")
        text_column.addWidget(title)
        text_column.addWidget(meta)
        row_layout.addLayout(text_column, 1)

        score = QLabel(f"{item.total:.1f}")
        score.setObjectName("ratingsRowScore")
        row_layout.addWidget(score)

        open_button = QPushButton("Open")
        open_button.setObjectName("ratingsOpenButton")
        open_button.clicked.connect(
            lambda _checked=False, current=item: self._open_rated_title(current)
        )
        row_layout.addWidget(open_button)
        return row

    def _open_rated_title(self, item: RatedTitleSummary) -> None:
        entry = self.library.get(item.media_type, item.tmdb_id)
        if entry is not None:
            self._open_library_entry(entry)
            return
        media = MediaSearchResult(
            tmdb_id=item.tmdb_id,
            media_type=item.media_type,
            title=item.title,
            year=item.year,
            overview=None,
            poster_path=item.poster_path,
        )
        self.current_media = media
        self._show_search_page()
        self._show_media_summary(media)
        self._load_library_state(media)
        self._load_rating_state(media)
        self._load_availability(media)

    def _backfill_library_classifications(self) -> None:
        if self._library_classification_running:
            return
        entries = self.library.list()
        unknown_count = sum(1 for entry in entries if entry.is_anime is None)
        if unknown_count == 0:
            return

        self._library_classification_running = True
        self.library_results_label.setText(
            f"Classifying {unknown_count} older library title(s) for Anime filtering…"
        )
        worker = AsyncWorker(lambda: self.library_classifier.backfill_unknown(entries))
        worker.signals.result.connect(self._handle_library_classification_result)
        worker.signals.error.connect(self._handle_library_classification_error)
        worker.signals.finished.connect(self._finish_library_classification)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_library_classification_result(self, _payload: object) -> None:
        self._library_dirty = True
        self._refresh_library_view()

    @Slot(str)
    def _handle_library_classification_error(self, message: str) -> None:
        self.library_results_label.setText(
            f"Could not finish Anime classification: {message}"
        )

    @Slot()
    def _finish_library_classification(self) -> None:
        self._library_classification_running = False

    def _refresh_library_view(self, *_args: object) -> None:
        if not hasattr(self, "library_grid"):
            return

        entries = self.library.list()
        ratings = self.ratings.list()
        totals = rating_totals(ratings)
        status_value = self.library_status_filter.currentData() or None
        content_filter = self.library_type_filter.currentData() or "all"
        sort_value = self.library_sort_combo.currentData() or "recent"
        filtered = prepare_library_entries(
            entries,
            query=self.library_search_input.text(),
            status=status_value,
            content_filter=content_filter,
            favourite_only=self.library_favourites_filter.isChecked(),
            sort_by=sort_value,
            ratings=totals,
        )

        watched = sum(1 for entry in entries if entry.status == "watched")
        watchlist = sum(1 for entry in entries if entry.status == "watchlist")
        favourites = sum(1 for entry in entries if entry.favourite)
        rated = sum(
            1
            for entry in entries
            if (entry.media_type, entry.tmdb_id) in totals
        )
        self.library_summary_label.setText(
            f"{len(entries)} title(s) • {watched} watched • {watchlist} watchlist • "
            f"{favourites} favourite(s) • {rated} rated"
        )
        self.library_results_label.setText(
            f"Showing {len(filtered)} of {len(entries)} saved title(s)."
        )

        self._clear_layout(self.library_grid)
        self._library_cards = []
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
            self.library_grid.addWidget(empty, 0, 0, 1, 1)
            self._library_dirty = False
            return

        self._library_cards = [
            self._build_library_card(
                entry,
                totals.get((entry.media_type, entry.tmdb_id)),
            )
            for entry in filtered
        ]
        self._reflow_library_grid()
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
            is_anime=entry.is_anime,
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
        self._recommendations_dirty = True
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
        self._ratings_dirty = True
        self._recommendations_dirty = True
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
            self._ratings_dirty = True
            self._recommendations_dirty = True
            self.status_label.setText(f"Removed {self.current_media.title} from your library.")
            return

        status: LibraryStatus = raw_status
        entry = self.library.upsert(self.current_media, status)
        self.favourite_checkbox.blockSignals(True)
        self.favourite_checkbox.setChecked(entry.favourite)
        self.favourite_checkbox.setEnabled(True)
        self.favourite_checkbox.blockSignals(False)
        self._library_dirty = True
        self._ratings_dirty = True
        self._recommendations_dirty = True
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
        self._ratings_dirty = True
        self._recommendations_dirty = True
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

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "library_scroll"):
            QTimer.singleShot(0, self._reflow_library_grid)
        if hasattr(self, "recommendations_grid"):
            QTimer.singleShot(0, self._reflow_recommendations_grid)

    def _reflow_library_grid(self) -> None:
        if not self._library_cards or not hasattr(self, "library_scroll"):
            return
        columns = responsive_column_count(
            self.library_scroll.viewport().width() - 16,
            220,
            14,
            max_columns=10,
        )
        self._reflow_card_grid(self.library_grid, self._library_cards, columns)

    def _reflow_recommendations_grid(self) -> None:
        if not self._recommendation_cards or not hasattr(self, "recommendation_scroll"):
            return
        columns = responsive_column_count(
            self.recommendation_scroll.viewport().width() - 16,
            350,
            14,
            max_columns=6,
        )
        self._reflow_card_grid(
            self.recommendations_grid,
            self._recommendation_cards,
            columns,
        )

    @staticmethod
    def _reflow_card_grid(
        grid: QGridLayout,
        cards: list[QWidget],
        columns: int,
    ) -> None:
        columns = max(1, columns)
        for card in cards:
            grid.removeWidget(card)
        for index, card in enumerate(cards):
            grid.addWidget(
                card,
                index // columns,
                index % columns,
                Qt.AlignmentFlag.AlignTop,
            )

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
