import json
from pathlib import Path
import tempfile

from mlb_hr.model.package import ModelPackage
from mlb_hr.resources_runtime import bundled_model_text,packaged_migrations_dir
from mlb_hr.storage.sqlite import SQLiteStore


def test_bundled_model_and_migrations_are_runtime_resources():
    raw=json.loads(bundled_model_text())
    assert raw['model_version']=='DEV-BASELINE-0.1'
    with tempfile.TemporaryDirectory() as td, packaged_migrations_dir() as migrations:
        st=SQLiteStore(Path(td)/'app.db',migrations);st.migrate()
        with st.connection() as con:
            version=con.execute('SELECT max(version) FROM schema_migrations').fetchone()[0]
        assert version==5
        model=Path(td)/'model';model.mkdir();(model/'model_manifest.json').write_text(json.dumps(raw),encoding='utf-8')
        assert ModelPackage(model).release_ready is False
