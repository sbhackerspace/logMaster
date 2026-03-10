import multiprocessing

# Binding
bind = "0.0.0.0:5000"

# Workers: 2-4 x CPUs is a common starting point for I/O-bound apps
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
threads = 1

# Timeouts
timeout = 60
keepalive = 5

# Logging — goes to journald via systemd
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "logMasterServer"
