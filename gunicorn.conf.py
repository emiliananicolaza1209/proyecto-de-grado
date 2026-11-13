"""Un proceso mantiene el límite de acceso compartido; PostgreSQL serializa escrituras."""
import os
bind = '0.0.0.0:' + os.getenv('PORT', '10000')
workers = 1
threads = 4
worker_class = 'gthread'
timeout = 60
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
preload_app = False
accesslog = '-'
errorlog = '-'
# No guardar consultas, cookies, referencias ni credenciales en el access log.
access_log_format = '%(m)s %(U)s %(s)s %(L)s'
