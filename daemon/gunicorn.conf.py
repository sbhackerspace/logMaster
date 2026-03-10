import multiprocessing

# Binding
bind = "0.0.0.0:5001"

# Workers: daemon spawns subprocesses for journalctl so keep worker count low
workers = multiprocessing.cpu_count()
worker_class = "sync"
threads = 1

# Timeouts — journalctl queries can take a moment
timeout = 60
keepalive = 5

# Logging — goes to journald via systemd
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "logMasterDaemon"
