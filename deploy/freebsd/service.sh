#!/bin/sh
# Unprivileged FreeBSD deployment. OpenList itself is never started/stopped here.
set -eu
ROOT=$(CDPATH= cd -P "$(dirname "$0")/../.." && pwd)
RUN="$ROOT/runtime"
mkdir -p "$RUN" "$ROOT/data"
chmod 700 "$ROOT" "$RUN" "$ROOT/data"
cd "$ROOT"
alive() { /usr/bin/pgrep -L -F "$RUN/$1-supervisor.pid" >/dev/null 2>&1; }
start_one() {
    name=$1
    shift
    if ! alive "$name"; then
        /usr/sbin/daemon -r -R 5 -P "$RUN/$name-supervisor.pid" -p "$RUN/$name.pid" \
            -o "$RUN/$name.log" -t "openlist-ai-$name" "$@" </dev/null >/dev/null 2>&1
    fi
}
stop_one() {
    if alive "$1"; then /usr/bin/pkill -TERM -L -F "$RUN/$1-supervisor.pid"; fi
}
case "${1:-status}" in
    start)
        exec /usr/bin/lockf -s -t 0 "$RUN/start.lock" /bin/sh "$0" _start
        ;;
    _start)
        umask 077
        if [ ! -f "$RUN/ai.disabled" ]; then
            start_one api "$ROOT/.venv312/bin/python" -m uvicorn aitags.app:app \
                --uds "$RUN/ai.sock" --workers 1 --no-access-log --timeout-graceful-shutdown 25
        fi
        start_one gateway /usr/local/sbin/nginx -e "$RUN/nginx-error.log" -p "$ROOT/" -c "$ROOT/deploy/freebsd/nginx.conf"
        ;;
    stop)
        stop_one gateway
        stop_one api
        ;;
    restart-api)
        stop_one api
        sleep 2
        exec /bin/sh "$0" start
        ;;
    restart-gateway)
        stop_one gateway
        sleep 2
        exec /bin/sh "$0" start
        ;;
    disable-ai)
        touch "$RUN/ai.disabled"
        stop_one api
        ;;
    enable-ai)
        rm -f "$RUN/ai.disabled"
        exec /bin/sh "$0" start
        ;;
    status)
        for name in api gateway; do
            if alive "$name"; then printf '%s running\n' "$name"; else printf '%s stopped\n' "$name"; fi
        done
        ;;
    *) printf 'Usage: %s start|stop|restart-api|restart-gateway|disable-ai|enable-ai|status\n' "$0" >&2; exit 2 ;;
esac
