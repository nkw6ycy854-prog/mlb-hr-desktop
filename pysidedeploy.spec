[app]
title = MLB HR
input_file = src/mlb_hr/app.py
project_dir = .
exec_directory = build
icon = /Users/sebastianrosario/Desktop/mlb_hr_desktop/.venv/lib/python3.13/site-packages/PySide6/scripts/deploy_lib/pyside_icon.icns

[python]
python_path = /Users/sebastianrosario/Desktop/mlb_hr_desktop/.venv/bin/python
packages = nuitka==4.1.3,ordered_set,zstandard,PySide6==6.11.1,duckdb==1.5.5,httpx==0.28.1,keyring==25.7.0,numpy==2.3.5,scikit-learn==1.8.0,scipy==1.17.0

[qt]
modules = Core,DBus,Gui,Widgets
qml_files = 
plugins = accessiblebridge,egldeviceintegrations,generic,iconengines,imageformats,platforminputcontexts,platforms,platforms/darwin,platformthemes,styles,wayland-decoration-client,wayland-graphics-integration-client,wayland-shell-integration,xcbglintegrations

[nuitka]
mode = onefile
extra_args = --quiet --noinclude-qt-translations --include-package-data=mlb_hr
macos.permissions = 

