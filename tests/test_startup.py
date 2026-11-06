import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from etacontrol import __main__ as bootstrap
from etacontrol import processes
from etacontrol.institution import PackageError


def test_cold_start_creates_shared_data_before_older_launcher_runs(tmp_path,monkeypatch):
    runtime=tmp_path/'.yerel'/('a'*64)/'runtime'
    runtime.mkdir(parents=True)
    (runtime/'launcher.py').write_text(
        "import os,json\nfrom pathlib import Path\n"
        "state=Path(os.environ['ETA_CONTROL_DATA'])/'server.json'\n"
        "assert state.parent.is_dir()\n"
        "state.write_text(json.dumps({'started':True}))\n",encoding='utf-8')
    monkeypatch.setattr(bootstrap,'ROOT',tmp_path)
    monkeypatch.setattr(bootstrap,'prepare',lambda:runtime)
    monkeypatch.setattr(bootstrap.sys,'argv',['etacontrol','--no-browser'])
    monkeypatch.setattr(processes.psutil,'process_iter',lambda *a:[])
    assert not (tmp_path/'data').exists()
    assert bootstrap.main()==0
    assert json.loads((tmp_path/'data/server.json').read_text())=={'started':True}
    marker=tmp_path/'data/keep.txt';marker.write_text('keep')
    assert bootstrap.main()==0 and marker.read_text()=='keep'


def test_install_check_does_not_create_data_or_recover_a_server(tmp_path,monkeypatch):
    monkeypatch.setattr(bootstrap,'ROOT',tmp_path)
    monkeypatch.setattr(bootstrap,'prepare',lambda:tmp_path)
    monkeypatch.setattr(bootstrap.sys,'argv',['etacontrol','--check'])
    monkeypatch.setattr(bootstrap.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    monkeypatch.setattr(processes,'recover',lambda *a:pytest.fail('No startup during check'))
    assert bootstrap.main()==0 and not (tmp_path/'data').exists()


class Process:
    def __init__(self,path,pid=123,created=12.0,ppid=0):
        self.pid=pid
        self.info=dict(pid=pid,ppid=ppid,cmdline=['python.exe',str(path),'--port','8767'],create_time=created)
    def is_running(self):return True
    def create_time(self):return 12.0


def test_orphaned_owned_server_is_recovered_without_starting_or_stopping_it(tmp_path,monkeypatch):
    process=Process(tmp_path/'.yerel'/('a'*64)/'runtime/server.py')
    monkeypatch.setattr(processes.psutil,'process_iter',lambda *a:[process])
    monkeypatch.setattr(processes.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(b'{"app_id":"eta-control-local"}'))
    processes.recover(tmp_path)
    assert json.loads((tmp_path/'data/server.json').read_text())==dict(pid=123,created=12.0,url='http://127.0.0.1:8767')
    # With state present, no process enumeration or metadata overwrite is needed.
    monkeypatch.setattr(processes.psutil,'process_iter',lambda *a:pytest.fail('Existing state must remain'))
    processes.recover(tmp_path)


def test_recovery_ignores_other_installations_nested_projects_and_reused_pid(tmp_path,monkeypatch):
    other=tmp_path.parent/'other/.yerel'/('b'*64)/'runtime/server.py'
    nested=tmp_path/'.yerel/lab/.yerel'/('b'*64)/'runtime/server.py'
    recycled=Process(tmp_path/'.yerel'/('a'*64)/'runtime/server.py',created=3.0)
    monkeypatch.setattr(processes.psutil,'process_iter',lambda *a:[Process(other),Process(nested),recycled])
    monkeypatch.setattr(processes.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(b'{"app_id":"eta-control-local"}'))
    processes.recover(tmp_path)
    assert not (tmp_path/'data').exists()


def test_ambiguous_orphans_block_a_third_server(tmp_path,monkeypatch):
    owned=tmp_path/'.yerel'/('a'*64)/'runtime/server.py'
    monkeypatch.setattr(processes.psutil,'process_iter',lambda *a:[Process(owned),Process(owned,pid=124)])
    monkeypatch.setattr(processes.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(b'{"app_id":"eta-control-local"}'))
    with pytest.raises(PackageError,match='birden fazla'):
        processes.recover(tmp_path)
    assert not (tmp_path/'data').exists()


def test_windows_venv_redirector_and_child_are_one_server(tmp_path,monkeypatch):
    owned=tmp_path/'.yerel'/('a'*64)/'runtime/server.py'
    monkeypatch.setattr(processes.psutil,'process_iter',lambda *a:[Process(owned),Process(owned,pid=124,ppid=123)])
    monkeypatch.setattr(processes.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(b'{"app_id":"eta-control-local"}'))
    processes.recover(tmp_path)
    assert json.loads((tmp_path/'data/server.json').read_text())['pid']==123


@pytest.mark.parametrize('busy',[False,True])
def test_stop_checks_jobs_and_stops_only_owned_server_children(tmp_path,monkeypatch,busy):
    owned=tmp_path/'.yerel'/('a'*64)/'runtime/server.py'
    calls=[]
    class Managed(Process):
        def cmdline(self):return self.info['cmdline']
        def terminate(self):calls.append(('terminate',self.pid))
        def wait(self,timeout):calls.append(('wait',self.pid))
        def children(self,recursive):return [child,other]
    parent=Managed(owned)
    child=Managed(owned,pid=124,ppid=123)
    other=Managed(tmp_path.parent/'other/server.py',pid=125,ppid=123)
    state=tmp_path/'data/server.json';state.parent.mkdir()
    state.write_text(json.dumps(dict(pid=123,created=12.0,url='http://127.0.0.1:8767')))
    monkeypatch.setattr(processes.psutil,'Process',lambda pid:parent)
    payload=json.dumps(dict(active='job' if busy else None)).encode()
    monkeypatch.setattr(processes.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(payload))
    if busy:
        with pytest.raises(PackageError,match='Terminal'):
            processes.stop(tmp_path)
        assert not calls and state.exists()
    else:
        processes.stop(tmp_path)
        assert ('terminate',123) in calls and ('terminate',124) in calls
        assert ('terminate',125) not in calls and not state.exists()
