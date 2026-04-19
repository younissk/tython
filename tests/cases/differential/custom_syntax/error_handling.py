class __TythonPanic(RuntimeError):
    pass

def panic(message) -> None:
    raise __TythonPanic(str(message))

class __TythonRecoverableError(Exception):
    pass
from dataclasses import dataclass

@dataclass(frozen=True)
class FileError(__TythonRecoverableError):
    path: str
    reason: str

def read_file(path: str) -> str:
    if path == '':
        raise FileError(path=path, reason='empty path')
    return 'ok'

def run(path: str) -> str:
    return read_file(path)
try:
    text = read_file('notes.txt')
    print(text)
except FileError as err:
    print(err.reason)
except __TythonRecoverableError as any:
    print('fallback')
finally:
    print('done')
panic('unreachable state')
