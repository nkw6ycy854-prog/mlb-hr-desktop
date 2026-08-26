from __future__ import annotations

from zoneinfo import available_timezones

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from mlb_hr.providers.secrets import SecretStore

STAKE_OPTIONS = ["$5", "$10", "$20", "$25", "$50"]
DENSITY_OPTIONS = [("Cómoda", "comfortable"), ("Compacta", "compact")]
AI_PROVIDER_OPTIONS = [
    ("Ninguno", "none"), ("Groq", "groq"), ("Gemini", "gemini"),
    ("OpenRouter", "openrouter"), ("Ollama local", "ollama"),
]


def _section(title: str, root: QVBoxLayout) -> QFormLayout:
    frame = QFrame()
    frame.setObjectName("card")
    frame_layout = QVBoxLayout(frame)
    label = QLabel(title)
    label.setObjectName("section")
    frame_layout.addWidget(label)
    form = QFormLayout()
    frame_layout.addLayout(form)
    root.addWidget(frame)
    return form


class SettingsWidget(QWidget):
    def __init__(self, store, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.secrets = SecretStore()
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 22)
        root.setSpacing(14)

        title = QLabel("AJUSTES")
        title.setObjectName("title")
        root.addWidget(title)
        note = QLabel("Las probabilidades y thresholds del modelo congelado no se editan desde aquí.")
        note.setObjectName("muted")
        root.addWidget(note)

        self._build_general(root)
        self._build_odds(root)
        self._build_ai(root)
        self._build_system(root)

        self.feedback = QLabel("")
        self.feedback.setObjectName("muted")
        self.feedback.setWordWrap(True)
        root.addWidget(self.feedback)

        save = QPushButton("GUARDAR")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save)
        root.addWidget(save)
        root.addStretch()

    def _build_general(self, root: QVBoxLayout) -> None:
        form = _section("GENERAL", root)
        self.stake = QComboBox()
        self.stake.addItems(STAKE_OPTIONS)
        current_stake = f"${int(self.store.get_state('default_stake', 10.0))}"
        if current_stake in STAKE_OPTIONS:
            self.stake.setCurrentText(current_stake)
        form.addRow("Apuesta base", self.stake)

        self.timezone = QComboBox()
        zones = sorted(available_timezones())
        self.timezone.addItems(zones)
        current_tz = str(self.store.get_state("timezone_name", "") or "")
        if current_tz and current_tz not in zones:
            self.timezone.addItem(current_tz)
        if current_tz:
            self.timezone.setCurrentText(current_tz)
        form.addRow("Zona horaria", self.timezone)

        self.density = QComboBox()
        for label, _code in DENSITY_OPTIONS:
            self.density.addItem(label)
        current_density = str(self.store.get_state("ui_density", "comfortable") or "comfortable")
        for label, code in DENSITY_OPTIONS:
            if code == current_density:
                self.density.setCurrentText(label)
        form.addRow("Densidad de interfaz", self.density)

    def _build_odds(self, root: QVBoxLayout) -> None:
        form = _section("CUOTAS", root)
        self.odds_key = QLineEdit()
        self.odds_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.odds_key.setPlaceholderText("The Odds API key")
        form.addRow("The Odds API", self.odds_key)
        fanduel_ref = QLabel("Activa · referencia del ledger")
        fanduel_ref.setObjectName("muted")
        form.addRow("FanDuel", fanduel_ref)
        best_price = QLabel("Automática · display/comparación")
        best_price.setObjectName("muted")
        form.addRow("Mejor cuota", best_price)
        us_books = QLabel("Sportsbooks USA reportados por The Odds API")
        us_books.setObjectName("muted")
        form.addRow("Sportsbooks", us_books)
        self.test_connection_btn = QPushButton("PROBAR CONEXIÓN")
        form.addRow(self.test_connection_btn)
        self.odds_feedback = QLabel("")
        self.odds_feedback.setObjectName("muted")
        self.odds_feedback.setWordWrap(True)
        form.addRow(self.odds_feedback)

    def _build_ai(self, root: QVBoxLayout) -> None:
        form = _section("IA", root)
        self.ai_provider = QComboBox()
        for label, _code in AI_PROVIDER_OPTIONS:
            self.ai_provider.addItem(label)
        current_provider = str(self.store.get_state("ai_provider", "none") or "none")
        for label, code in AI_PROVIDER_OPTIONS:
            if code == current_provider:
                self.ai_provider.setCurrentText(label)
        form.addRow("Proveedor", self.ai_provider)

        self.ai_review_enabled = QCheckBox("Activar revisión IA")
        self.ai_review_enabled.setChecked(bool(self.store.get_state("ai_review_enabled", False)))
        form.addRow(self.ai_review_enabled)

        self.groq_key = QLineEdit()
        self.groq_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Groq API key", self.groq_key)
        self.groq_model = QLineEdit(str(self.store.get_state("groq_model", "")))
        form.addRow("Modelo Groq", self.groq_model)

        self.gemini_key = QLineEdit()
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Gemini API key", self.gemini_key)
        self.gemini_model = QLineEdit(str(self.store.get_state("gemini_model", "")))
        form.addRow("Modelo Gemini", self.gemini_model)

        self.openrouter_key = QLineEdit()
        self.openrouter_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("OpenRouter API key", self.openrouter_key)
        self.openrouter_model = QLineEdit(str(self.store.get_state("openrouter_model", "")))
        form.addRow("Modelo OpenRouter", self.openrouter_model)

        self.ollama_model = QLineEdit(str(self.store.get_state("ollama_model", "")))
        form.addRow("Modelo Ollama local", self.ollama_model)

        self.test_ai_btn = QPushButton("PROBAR IA")
        form.addRow(self.test_ai_btn)
        self.ai_feedback = QLabel("")
        self.ai_feedback.setObjectName("muted")
        self.ai_feedback.setWordWrap(True)
        form.addRow(self.ai_feedback)

    def _build_system(self, root: QVBoxLayout) -> None:
        form = _section("SISTEMA", root)
        self.statcast_status = QLabel("—")
        form.addRow("Statcast", self.statcast_status)
        self.model_status = QLabel("—")
        form.addRow("Modelo", self.model_status)
        self.db_status = QLabel("—")
        form.addRow("Base de datos", self.db_status)
        self.last_selftest = QLabel(str(self.store.get_state("last_selftest_at", "Nunca ejecutado")))
        form.addRow("Último self-test", self.last_selftest)
        self.open_data_folder_btn = QPushButton("ABRIR CARPETA DE DATOS")
        form.addRow(self.open_data_folder_btn)
        self.run_selftest_btn = QPushButton("EJECUTAR SELF-TEST")
        form.addRow(self.run_selftest_btn)
        self.selftest_feedback = QLabel("")
        self.selftest_feedback.setObjectName("muted")
        self.selftest_feedback.setWordWrap(True)
        form.addRow(self.selftest_feedback)

    def save(self) -> None:
        changed: list[str] = []
        restart_needed = False

        stake_value = float(self.stake.currentText().replace("$", ""))
        if stake_value != float(self.store.get_state("default_stake", 10.0)):
            changed.append("Apuesta base")
        self.store.set_state("default_stake", stake_value)

        tz_value = self.timezone.currentText()
        if tz_value != str(self.store.get_state("timezone_name", "") or ""):
            changed.append("Zona horaria")
        self.store.set_state("timezone_name", tz_value)

        density_label = self.density.currentText()
        density_code = next((code for label, code in DENSITY_OPTIONS if label == density_label), "comfortable")
        if density_code != str(self.store.get_state("ui_density", "comfortable") or "comfortable"):
            changed.append("Densidad de interfaz")
        self.store.set_state("ui_density", density_code)

        provider_label = self.ai_provider.currentText()
        provider_code = next((code for label, code in AI_PROVIDER_OPTIONS if label == provider_label), "none")
        if provider_code != str(self.store.get_state("ai_provider", "none") or "none"):
            changed.append("Proveedor IA")
            restart_needed = True
        self.store.set_state("ai_provider", provider_code)

        review_enabled = self.ai_review_enabled.isChecked()
        if review_enabled != bool(self.store.get_state("ai_review_enabled", False)):
            changed.append("Revisión IA")
        self.store.set_state("ai_review_enabled", review_enabled)

        secrets = [
            ("THE_ODDS_API_KEY", self.odds_key, "Odds API"),
            ("GROQ_API_KEY", self.groq_key, "Groq"),
            ("GEMINI_API_KEY", self.gemini_key, "Gemini"),
            ("OPENROUTER_API_KEY", self.openrouter_key, "OpenRouter"),
        ]
        failed: list[str] = []
        for key, field, label in secrets:
            if field.text().strip():
                if self.secrets.set(key, field.text().strip()):
                    changed.append(label)
                    restart_needed = True
                else:
                    failed.append(label)

        for state_key, field, label in [
            ("groq_model", self.groq_model, "Modelo Groq"),
            ("gemini_model", self.gemini_model, "Modelo Gemini"),
            ("openrouter_model", self.openrouter_model, "Modelo OpenRouter"),
            ("ollama_model", self.ollama_model, "Modelo Ollama local"),
        ]:
            new_value = field.text().strip()
            if new_value != str(self.store.get_state(state_key, "") or ""):
                changed.append(label)
                restart_needed = True
            self.store.set_state(state_key, new_value)

        if failed:
            self.feedback.setText(
                "Guardado con errores. No se pudieron guardar en el keyring del sistema: " + ", ".join(failed)
            )
            self.feedback.setObjectName("warning")
        else:
            parts = ["Guardado."]
            if changed:
                parts.append("Cambios: " + ", ".join(changed) + ".")
            if restart_needed:
                parts.append("Reinicia la app para recargar los providers configurados.")
            self.feedback.setText(" ".join(parts))
            self.feedback.setObjectName("good")
