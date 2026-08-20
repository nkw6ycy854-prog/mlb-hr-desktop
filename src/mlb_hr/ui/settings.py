from __future__ import annotations

from PySide6.QtWidgets import QFormLayout,QLabel,QLineEdit,QMessageBox,QPushButton,QVBoxLayout,QWidget

from mlb_hr.providers.secrets import SecretStore


class SettingsWidget(QWidget):
    def __init__(self,store,parent=None)->None:
        super().__init__(parent);self.store=store;self.secrets=SecretStore();self._build()

    def _build(self)->None:
        root=QVBoxLayout(self);root.setContentsMargins(22,18,22,22);root.setSpacing(14)
        t=QLabel("AJUSTES");t.setObjectName("title");root.addWidget(t)
        note=QLabel("Las probabilidades y thresholds del modelo congelado no se editan desde aquí.");note.setObjectName("muted");root.addWidget(note)
        form=QFormLayout();root.addLayout(form)
        self.odds_key=QLineEdit();self.odds_key.setEchoMode(QLineEdit.EchoMode.Password);self.odds_key.setPlaceholderText("The Odds API key");form.addRow("Odds API",self.odds_key)
        self.groq_key=QLineEdit();self.groq_key.setEchoMode(QLineEdit.EchoMode.Password);form.addRow("Groq (opcional)",self.groq_key)
        self.gemini_key=QLineEdit();self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password);form.addRow("Gemini (opcional)",self.gemini_key)
        self.openrouter_key=QLineEdit();self.openrouter_key.setEchoMode(QLineEdit.EchoMode.Password);form.addRow("OpenRouter (opcional)",self.openrouter_key)
        self.groq_model=QLineEdit(str(self.store.get_state("groq_model","")));form.addRow("Modelo Groq",self.groq_model)
        self.gemini_model=QLineEdit(str(self.store.get_state("gemini_model","")));form.addRow("Modelo Gemini",self.gemini_model)
        self.openrouter_model=QLineEdit(str(self.store.get_state("openrouter_model","")));form.addRow("Modelo OpenRouter",self.openrouter_model)
        self.ollama_model=QLineEdit(str(self.store.get_state("ollama_model","")));form.addRow("Modelo Ollama local",self.ollama_model)
        save=QPushButton("GUARDAR");save.setObjectName("primaryButton");save.clicked.connect(self.save);root.addWidget(save);root.addStretch()

    def save(self)->None:
        secrets=[("THE_ODDS_API_KEY",self.odds_key),("GROQ_API_KEY",self.groq_key),("GEMINI_API_KEY",self.gemini_key),("OPENROUTER_API_KEY",self.openrouter_key)]
        failed=[]
        for key,field in secrets:
            if field.text().strip() and not self.secrets.set(key,field.text().strip()):failed.append(key)
        self.store.set_state("groq_model",self.groq_model.text().strip());self.store.set_state("gemini_model",self.gemini_model.text().strip());self.store.set_state("openrouter_model",self.openrouter_model.text().strip());self.store.set_state("ollama_model",self.ollama_model.text().strip())
        if failed:QMessageBox.warning(self,"Ajustes","No se pudieron guardar algunas claves en el keyring del sistema: "+", ".join(failed))
        else:QMessageBox.information(self,"Ajustes","Guardado. Reinicia la app para recargar providers configurados.")
