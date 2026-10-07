"""One background job at a time (NAND flashing, data partition init...), with a live log."""
import subprocess
import threading
import time


class Job:
    def __init__(self, title, cmd):
        self.id = int(time.time() * 1000) % 100000000
        self.title = title
        self.cmd = cmd                     # list[str] or shell string
        self.lines = []
        self.status = "running"            # running | done | failed
        self.rc = None
        self.started = time.time()
        self.finished = None

    def run(self):
        shell = isinstance(self.cmd, str)
        try:
            p = subprocess.Popen(self.cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, errors="replace", bufsize=1)
            for line in p.stdout:
                self.lines.append(line.rstrip("\n"))
            p.wait()
            self.rc = p.returncode
        except Exception as ex:  # noqa: BLE001
            self.lines.append(f"!! {ex}")
            self.rc = -1
        self.finished = time.time()
        self.status = "done" if self.rc == 0 else "failed"
        self.lines.append(f"-- exit {self.rc} after {self.finished - self.started:.0f} s")

    def as_dict(self):
        return {"id": self.id, "title": self.title, "status": self.status, "rc": self.rc,
                "lines": self.lines, "started": self.started, "finished": self.finished}


class Runner:
    def __init__(self):
        self.lock = threading.Lock()
        self.current = None
        self.history = []

    def busy(self):
        return self.current is not None and self.current.status == "running"

    def start(self, title, cmd):
        with self.lock:
            if self.busy():
                raise RuntimeError(f"job '{self.current.title}' is still running")
            job = Job(title, cmd)
            self.current = job
            self.history.append(job)
            self.history = self.history[-10:]
            threading.Thread(target=job.run, daemon=True).start()
            return job

    def get(self, job_id):
        for j in self.history:
            if j.id == job_id:
                return j
        return None


runner = Runner()


def run_quick(cmd, timeout=60):
    """synchronous helper for short commands: (rc, output)"""
    shell = isinstance(cmd, str)
    try:
        p = subprocess.run(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors="replace", timeout=timeout)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return -1, f"timeout after {timeout} s"
    except FileNotFoundError as ex:
        return -1, str(ex)
