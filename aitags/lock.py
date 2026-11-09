"""OS-held lock; automatically released if the worker process crashes."""
import os


class WorkerLock:
    def __init__(self,path):
        self.file=open(path,'a+b')
        if os.fstat(self.file.fileno()).st_size==0:
            self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError('同一数据库已有工作进程，请使用单进程、单副本部署') from None

    def close(self):
        if self.file.closed:return
        self.file.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
        self.file.close()
