module.exports = {
  apps: [{
    name: 'FRIDAY',
    script: 'main.py',
    interpreter: 'python3',
    cwd: '/Users/fs/Documents/FRIDAY',
    watch: false,
    autorestart: true,
    restart_delay: 3000,
    max_restarts: 10,
    env: {
      PYTHONUNBUFFERED: '1',
    },
    log_file: '/Users/fs/Documents/FRIDAY/logs/pm2.log',
    error_file: '/Users/fs/Documents/FRIDAY/logs/pm2-error.log',
    out_file: '/Users/fs/Documents/FRIDAY/logs/pm2-out.log',
  }]
}
