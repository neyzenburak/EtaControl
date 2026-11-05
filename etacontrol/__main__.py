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
            result=subprocess.run([sys.executable,str(runtime/'launcher.py'),*sys.argv[1:]],cwd=runtime,env=environment())
        return result.returncode
    except (PackageError,OSError,ValueError) as exc:
        print(f'EtaControl: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
