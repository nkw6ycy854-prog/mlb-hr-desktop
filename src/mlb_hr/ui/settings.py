from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import available_timezones

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from mlb_hr.ai.providers import GeminiProvider, OllamaProvider, OpenAICompatibleProvider
from mlb_hr.providers.odds import OddsProvider
from mlb_hr.providers.secrets import SecretStore
from mlb_hr.selftest import run_self_test
from mlb_hr.ui.workers import FunctionWorker

STAKE_OPTIONS = ["$5", "$10", "$20", "$25", "$50"]
DENSITY_OPTIONS = [("Cómoda", "comfortable"), ("Compacta", "compact")]
AI_PROVIDER_OPTIONS = [
    ("Ninguno", "none"), ("Groq", "groq"), ("Gemini", "gemini"),
    ("OpenRouter", "openrouter"), ("Ollama local", "ollama"),
]


def _default_ai_provider_builder(provider_code: str, api_key: str, model: str):
    if provider_code == "groq":
        return OpenAICompatibleProvider(name="groq", endpoint="https://api.groq.com/openai/v1/chat/completions", api_key=api_key, model=model)
    if provider_code == "gemini":
        return GeminiProvider(api_key, model)
    if provider_code == "openrouter":
        return OpenAICompatibleProvider(name="openrouter", endpoint="https://openrouter.ai/api/v1/chat/completions", api_key=api_key, model=model)
    if provider_code == "ollama":
        return OllamaProvider(model)
    raise ValueError("Proveedor de IA no reconocido")


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
    def __init__(
        self, store, parent=None, *,
        paths=None,
        odds_provider_factory=None,
        ai_provider_builder=None,
        self_test_runner=None,
        open_url_func=None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.secrets = SecretStore()
        self._paths_override = paths
        self.odds_provider_factory = odds_provider_factory or (lambda api_key: OddsProvider(api_key))
        self.ai_provider_builder = ai_provider_builder or _default_ai_provider_builder
        self.self_test_runner = self_test_runner or run_self_test
        self.open_url_func = open_url_func or (lambda url: QDesktopServices.openUrl(url))
        self.thread_pool = QThreadPool.globalInstance()
        self._build()

    @property
    def paths(self):
        if self._paths_override is None:
            from mlb_hr.storage.paths import resolve_app_paths
            self._paths_override = resolve_app_paths()
        return self._paths_override

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
        self.test_connection_btn.clicked.connect(self._test_connection)
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
        self.test_ai_btn.clicked.connect(self._test_ai)
        form.addRow(self.test_ai_btn)
        self.ai_feedback = QLabel("")
        self.ai_feedback.setObjectName("muted")
        self.ai_feedback.setWordWrap(True)
        form.addRow(self.ai_feedback)

    def _build_system(self, root: QVBoxLayout) -> None:
        form = _section("SISTEMA", root)
        self.statcast_status = QLabel("● —")
        form.addRow("Statcast", self.statcast_status)
        self.model_status = QLabel("● —")
        form.addRow("Modelo", self.model_status)
        self.db_status = QLabel("● —")
        form.addRow("Base de datos", self.db_status)
        self.last_selftest = QLabel(self._initial_selftest_text())
        form.addRow("Último self-test", self.last_selftest)
        self.open_data_folder_btn = QPushButton("ABRIR CARPETA DE DATOS")
        self.open_data_folder_btn.clicked.connect(self._open_data_folder)
        form.addRow(self.open_data_folder_btn)
        self.run_selftest_btn = QPushButton("EJECUTAR SELF-TEST")
        self.run_selftest_btn.clicked.connect(self._run_self_test)
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

    def _test_connection(self) -> None:
        self.test_connection_btn.setEnabled(False)
        self.odds_feedback.setText("Probando conexión…")
        self.odds_feedback.setObjectName("muted")
        api_key = self.odds_key.text().strip() or self.secrets.get("THE_ODDS_API_KEY")
        provider = self.odds_provider_factory(api_key)
        worker = FunctionWorker(provider.test_connection)
        self._connection_worker = worker
        worker.signals.finished.connect(self._connection_tested)
        worker.signals.error.connect(self._connection_test_error)
        self.thread_pool.start(worker)

    def _connection_tested(self, result) -> None:
        self.test_connection_btn.setEnabled(True)
        if result.data:
            self.odds_feedback.setText("Conexión OK")
            self.odds_feedback.setObjectName("good")
        else:
            self.odds_feedback.setText(f"Error: {result.error_message or 'sin detalle'}")
            self.odds_feedback.setObjectName("warning")

    def _connection_test_error(self, msg: str) -> None:
        self.test_connection_btn.setEnabled(True)
        self.odds_feedback.setText(f"Error: {msg}")
        self.odds_feedback.setObjectName("warning")

    def _test_ai(self) -> None:
        provider_label = self.ai_provider.currentText()
        provider_code = next((code for label, code in AI_PROVIDER_OPTIONS if label == provider_label), "none")
        key_model_fields = {
            "groq": (self.groq_key, self.groq_model),
            "gemini": (self.gemini_key, self.gemini_model),
            "openrouter": (self.openrouter_key, self.openrouter_model),
            "ollama": (None, self.ollama_model),
        }
        if provider_code not in key_model_fields:
            self.ai_feedback.setText("Selecciona un proveedor de IA para probar.")
            self.ai_feedback.setObjectName("warning")
            return
        key_field, model_field = key_model_fields[provider_code]
        api_key = (key_field.text().strip() if key_field else "") or self.secrets.get(f"{provider_code.upper()}_API_KEY") or ""
        model = model_field.text().strip()

        self.test_ai_btn.setEnabled(False)
        self.ai_feedback.setText("Probando IA…")
        self.ai_feedback.setObjectName("muted")
        try:
            provider = self.ai_provider_builder(provider_code, api_key, model)
        except Exception as exc:
            self.test_ai_btn.setEnabled(True)
            self.ai_feedback.setText(f"Error: {exc}")
            self.ai_feedback.setObjectName("warning")
            return
        worker = FunctionWorker(provider.review, "SELFTEST", {"probe": True})
        self._ai_worker = worker
        worker.signals.finished.connect(self._ai_tested)
        worker.signals.error.connect(self._ai_test_error)
        self.thread_pool.start(worker)

    def _ai_tested(self, review) -> None:
        self.test_ai_btn.setEnabled(True)
        if review.available:
            self.ai_feedback.setText(f"{review.provider} ({review.model}) respondió correctamente.")
            self.ai_feedback.setObjectName("good")
        else:
            self.ai_feedback.setText(f"{review.provider}: {review.error or 'sin respuesta'}")
            self.ai_feedback.setObjectName("warning")

    def _ai_test_error(self, msg: str) -> None:
        self.test_ai_btn.setEnabled(True)
        self.ai_feedback.setText(f"Error: {msg}")
        self.ai_feedback.setObjectName("warning")

    def _open_data_folder(self) -> None:
        self.open_url_func(QUrl.fromLocalFile(str(self.paths.data_dir)))

    def _run_self_test(self) -> None:
        self.run_selftest_btn.setEnabled(False)
        self.selftest_feedback.setText("Ejecutando self-test…")
        self.selftest_feedback.setObjectName("muted")
        worker = FunctionWorker(self.self_test_runner, require_runtime_data=True)
        self._selftest_worker = worker
        worker.signals.finished.connect(self._self_test_done)
        worker.signals.error.connect(self._self_test_error)
        self.thread_pool.start(worker)

    def _self_test_done(self, result: dict) -> None:
        self.run_selftest_btn.setEnabled(True)
        now_iso = datetime.now(timezone.utc).isoformat()
        passed = bool(result.get("passed"))
        self.store.set_state("last_selftest_at", now_iso)
        self.store.set_state("last_selftest_passed", passed)
        self.last_selftest.setText(self._selftest_label(passed, now_iso))
        self.last_selftest.setObjectName("good" if passed else "warning")
        if passed:
            self.selftest_feedback.setText("PASS")
            self.selftest_feedback.setObjectName("good")
        else:
            failed = [k for k, v in result.get("checks", {}).items() if not v]
            self.selftest_feedback.setText("FAIL: " + ", ".join(failed))
            self.selftest_feedback.setObjectName("warning")

    def _self_test_error(self, msg: str) -> None:
        self.run_selftest_btn.setEnabled(True)
        self.selftest_feedback.setText(f"Error: {msg}")
        self.selftest_feedback.setObjectName("warning")

    def _initial_selftest_text(self) -> str:
        last_at = self.store.get_state("last_selftest_at", None)
        last_passed = self.store.get_state("last_selftest_passed", None)
        if last_at and last_passed is not None:
            return self._selftest_label(bool(last_passed), str(last_at))
        return "● NO EJECUTADO"

    @staticmethod
    def _selftest_label(passed: bool, iso_text: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_text)
        except ValueError:
            time_text = iso_text
        else:
            time_text = dt.astimezone().strftime("%I:%M %p").lstrip("0")
        return f"● {'PASS' if passed else 'FAIL'} · {time_text}"

    def apply_health_report(self, report) -> None:
        model_item = next((i for i in report.items if i.key == "model"), None)
        if model_item:
            self.model_status.setText(f"● {model_item.detail} · {model_item.state}")
            self.model_status.setObjectName("good" if model_item.state == "OK" else "warning")
        statcast_item = next((i for i in report.items if i.key == "statcast"), None)
        if statcast_item:
            self.statcast_status.setText(f"● {statcast_item.state} · {statcast_item.detail}")
            self.statcast_status.setObjectName("good" if statcast_item.state == "OK" else "warning")
        db_item = next((i for i in report.items if i.key == "database"), None)
        if db_item:
            self.db_status.setText(f"● {db_item.state}")
            self.db_status.setObjectName("good" if db_item.state == "OK" else "warning")
