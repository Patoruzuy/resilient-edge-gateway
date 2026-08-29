#!/usr/bin/env bash
set -e

if [ "$#" -lt 2 ]; then
    echo "Usage:"
    echo "  netem_control.sh show <interface>"
    echo "  netem_control.sh clear <interface>"
    echo "  netem_control.sh degraded <interface> <delay_ms> <loss_pct>"
    echo "  netem_control.sh outage <interface>"
    exit 1
fi

action="$1"
interface="$2"

case "$action" in
    show)
        sudo tc qdisc show dev "$interface"
        ;;
    clear)
        sudo tc qdisc del dev "$interface" root 2>/dev/null || true
        sudo tc qdisc show dev "$interface"
        ;;
    degraded)
        delay_ms="$3"
        loss_pct="$4"
        sudo tc qdisc replace dev "$interface" root netem \
            delay "${delay_ms}ms" \
            loss "${loss_pct}%"
        sudo tc qdisc show dev "$interface"
        ;;
    outage)
        sudo tc qdisc replace dev "$interface" root netem \
            loss 100%

        sudo tc qdisc show dev "$interface"
        ;;
    *)
        echo "Unknown action: $action"
        exit 1
        ;;
esac
