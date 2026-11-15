"""On PYTHONPATH for tools/build_g3.py's build processes only. Runs the
interpreter's own sitecustomize (which this file would otherwise hide), then
installs the keystone branch guard (ks_guard.py)."""
import importlib.util,os,sys
_here=os.path.dirname(os.path.abspath(__file__))
for _p in sys.path:
 _f=os.path.join(_p or '.','sitecustomize.py')
 if os.path.abspath(_p or '.')!=_here and os.path.isfile(_f):
  _s=importlib.util.spec_from_file_location('_system_sitecustomize',_f);_m=importlib.util.module_from_spec(_s);_s.loader.exec_module(_m);break
sys.path.insert(0,_here)
try:
 import ks_guard;ks_guard.install()
except ImportError:pass   # keystone not installed in this interpreter
