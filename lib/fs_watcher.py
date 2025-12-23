
import os
import sys
import time
import select
from pathlib import Path
from typing import Optional

class FileWatcher:
    """
    Efficient file monitoring using kqueue on macOS/BSD, falling back to polling on others.
    """
    def __init__(self):
        self._use_kqueue = sys.platform == "darwin" or sys.platform.startswith("freebsd")
        
    def wait_for_change(self, path: Path, timeout: float = 1.0) -> bool:
        """
        Block until the file at 'path' is modified or timeout expires.
        Returns True if an event was detected, False on timeout.
        """
        if not path or not path.exists():
            time.sleep(min(timeout, 0.1))
            return False

        if not self._use_kqueue:
            # Fallback: simple sleep (caller loop handles the check)
            time.sleep(min(timeout, 0.05))
            return True

        # kqueue implementation
        fd = None
        try:
            fd = os.open(str(path), os.O_RDONLY)
            kq = select.kqueue()
            
            # Monitor for Write, Extend (append), Delete, Rename
            # NOTE_DELETE/RENAME implies the file was replaced (atomic write), 
            # which is a change we want to catch to trigger a re-read/re-open.
            ke = select.kevent(
                fd,
                filter=select.KQ_FILTER_VNODE,
                flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE | select.KQ_EV_ONESHOT,
                fflags=select.KQ_NOTE_WRITE | select.KQ_NOTE_EXTEND | select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME
            )
            
            events = kq.control([ke], 1, timeout)
            return bool(events)
            
        except OSError:
            # Fallback if file open fails or other OS error
            time.sleep(min(timeout, 0.05))
            return True
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
