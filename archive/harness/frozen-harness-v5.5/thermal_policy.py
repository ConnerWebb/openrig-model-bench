"""Optional sensor reads must never disable the essential resource guard."""
import pathlib

def temperatures(paths=None, read=None):
 paths=pathlib.Path('/sys/class/hwmon').glob('hwmon*/temp*_input') if paths is None else paths
 read=(lambda p:p.read_text()) if read is None else read
 values,errors={},{}
 try:
  for path in paths:
   try:values[str(path)]=int(read(path).strip())
   except (OSError,ValueError) as exc:errors[str(path)]={'type':type(exc).__name__,'errno':getattr(exc,'errno',None),'error':str(exc)}
 except OSError as exc:errors['sensor-enumeration']={'type':type(exc).__name__,'errno':exc.errno,'error':str(exc)}
 return values,errors
