# Reproducible inputs for the unsigned native workstation.
from pathlib import Path
import sys

scripts = Path(SPECPATH)
root = scripts.parent
runtime = Path(sys.base_prefix)
notices = [(str(runtime / "LICENSE.txt"), "notices/python")]
notices.append((str(scripts / "notices" / "tcl-license.terms"), "notices/tcl"))
notices.append((str(runtime / "tcl" / "tk8.6" / "license.terms"), "notices/tk"))
icon = str(scripts / "eai_desktop.ico")
a = Analysis([str(scripts / "eai_desktop_entry.py")], pathex=[str(root)],
             datas=[(icon, "assets")] + notices, hiddenimports=[],
             hookspath=[], runtime_hooks=[], excludes=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="EAI",
          console=False, icon=icon, strip=False, upx=False)
