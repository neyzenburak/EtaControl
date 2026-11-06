"""Ortak altyapı ile yerel kurum çalışma zamanını başlatır."""
from pathlib import Path
import subprocess
import sys

from .institution import ROOT, PackageError, environment, prepare


def main():
    try:
        if '--stop' in sys.argv:
            from .processes import stop
            stop()
            return 0
        runtime=prepare()
        if '--check' in sys.argv:
            result=subprocess.run([sys.executable,'-m','eta_app.install_check'],cwd=runtime,env=environment())
        else:
            env=environment(ROOT)
            # Older institution launchers create a runtime-local data directory,
            # while their state file points at the shared installation directory.
            # Create the actual parent before a server process can be spawned.
            Path(env['ETA_CONTROL_DATA']).mkdir(parents=True,exist_ok=True)
            from .processes import recover
            recover(ROOT)
            result=subprocess.run([sys.executable,str(runtime/'launcher.py'),*sys.argv[1:]],cwd=runtime,env=env)
        return result.returncode
    except (PackageError,OSError,ValueError) as exc:
        print(f'EtaControl: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
