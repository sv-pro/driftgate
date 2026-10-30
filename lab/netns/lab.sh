#!/usr/bin/env bash
# driftgate lab on Linux network namespaces + FRRouting. Needs root, iproute2, nftables, frr.
#
#   lab.sh up [--ttl 2h]   build the lab and write a lease (default 2h)
#   lab.sh down            tear everything down (idempotent)
#   lab.sh status          nodes, lease, BGP session
#   lab.sh extend <dur>    push the lease end forward (a human action)
#   lab.sh reap            tear down if the lease has expired (run from cron/systemd timer)
#
# Topology (all addresses are documentation / private ranges):
#
#   edge-cust 10.0.0.2 ──underlay── 10.0.0.1 edge-sc 10.0.1.1 ── 10.0.1.2 filter ── sw1
#            172.16.0.2 ═══ GRE ═══ 172.16.0.1
#   BGP 65002 ⇄ 65001 over GRE; edge-cust announces 198.51.100.0/24.
#   sw1 is a node driftgate does not model (drift class E).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${DG_LAB_STATE:-/var/lib/driftgate-lab}"
LEASE="$STATE_DIR/lease"
NODES=(dg-sc dg-cust dg-filter dg-sw1)
FRR_NODES=(sc cust)            # FRR pathspace names; namespace is dg-<name>
FRR_DAEMONS=(zebra staticd bgpd)

die() { echo "lab: $*" >&2; exit 1; }
need_root() { [ "$(id -u)" -eq 0 ] || die "needs root"; }

to_seconds() {                 # 90m, 2h, 1d, or plain seconds
  local v="$1" n="${1%[smhd]}"
  case "$v" in
    *s) echo "$n" ;; *m) echo $((n * 60)) ;; *h) echo $((n * 3600)) ;; *d) echo $((n * 86400)) ;;
    *[!0-9]*|'') die "bad duration: $v" ;; *) echo "$v" ;;
  esac
}

ns() { ip netns exec "$1" "${@:2}"; }

link_pair() {                  # link_pair nsA ifA addrA nsB ifB addrB
  ip link add "$2" netns "$1" type veth peer name "$5" netns "$4"
  ns "$1" ip addr add "$3" dev "$2"; ns "$1" ip link set "$2" up
  ns "$4" ip addr add "$6" dev "$5"; ns "$4" ip link set "$5" up
}

# The customer tunnel. GRE is what the scenario means; some kernels (containers, CI
# sandboxes) lack ip_gre, so DG_TUNNEL=vxlan gives the same L3 overlay without it.
TUNNEL="${DG_TUNNEL:-gre}"
make_tunnel() {                # make_tunnel <ns> <ifname> <local> <remote> <inner/cidr>
  case "$TUNNEL" in
    gre)   ns "$1" ip tunnel add "$2" mode gre local "$3" remote "$4" ttl 64 \
             || die "GRE unavailable in this kernel; retry with DG_TUNNEL=vxlan" ;;
    vxlan) ns "$1" ip link add "$2" type vxlan id 100 local "$3" remote "$4" dstport 4789 ;;
    *)     die "DG_TUNNEL must be gre or vxlan" ;;
  esac
  ns "$1" ip addr add "$5" dev "$2"; ns "$1" ip link set "$2" up
}

start_frr() {                  # start_frr <name>
  local name="$1" netns="dg-$1" etc="/etc/frr/$1" run="/var/run/frr/$1"
  mkdir -p "$etc" "$run"
  cp "$HERE/configs/$name.conf" "$etc/frr.conf"
  : > "$etc/vtysh.conf"
  chown -R frr:frr "$etc" "$run"
  for d in "${FRR_DAEMONS[@]}"; do
    ns "$netns" "/usr/lib/frr/$d" -d -N "$name" -f "$etc/frr.conf" -A 127.0.0.1 \
      -i "$run/$d.pid" >/dev/null
  done
}

stop_frr() {
  local name="$1" run="/var/run/frr/$1" pid
  for d in "${FRR_DAEMONS[@]}"; do
    if [ -f "$run/$d.pid" ]; then
      pid="$(cat "$run/$d.pid")"; kill "$pid" 2>/dev/null || true
    fi
  done
  rm -rf "$run" "/etc/frr/$name"
}

cmd_up() {
  need_root
  local ttl=7200
  if [ "${1:-}" = "--ttl" ]; then ttl="$(to_seconds "${2:?}")"; fi
  if ip netns list | grep -q '^dg-'; then die "lab already up (lab.sh down first)"; fi
  mkdir -p "$STATE_DIR"
  # The lease is written BEFORE anything is created: a crash half-way leaves a lease
  # that reap/down will clean, never resources without a lease.
  local now; now="$(date +%s)"
  printf 'created=%s\nexpires=%s\n' "$now" $((now + ttl)) > "$LEASE"

  for n in "${NODES[@]}"; do ip netns add "$n"; ns "$n" ip link set lo up; done
  for n in dg-sc dg-cust; do ns "$n" ip addr add "10.255.0.$([ $n = dg-sc ] && echo 1 || echo 2)/32" dev lo; done

  link_pair dg-cust cust-eth0 10.0.0.2/30  dg-sc sc-eth0 10.0.0.1/30
  link_pair dg-sc   sc-eth1   10.0.1.1/30  dg-filter flt-eth0 10.0.1.2/30
  link_pair dg-filter flt-eth1 10.0.2.1/30 dg-sw1 sw-eth0 10.0.2.2/30
  ns dg-sw1 ip link add br0 type bridge && ns dg-sw1 ip link set br0 up

  make_tunnel dg-sc   gre-cust 10.0.0.1 10.0.0.2 172.16.0.1/30
  make_tunnel dg-cust gre-sc   10.0.0.2 10.0.0.1 172.16.0.2/30
  ns dg-filter sysctl -qw net.ipv4.ip_forward=1
  ns dg-filter nft -f "$HERE/configs/filter.nft"

  for n in "${FRR_NODES[@]}"; do start_frr "$n"; done
  echo "lab up; lease expires $(date -d @$((now + ttl)) '+%F %T')"
}

cmd_down() {
  need_root
  for n in "${FRR_NODES[@]}"; do stop_frr "$n"; done
  for n in "${NODES[@]}"; do ip netns del "$n" 2>/dev/null || true; done
  rm -f "$LEASE"
  echo "lab down"
}

lease_get() { grep "^$1=" "$LEASE" | cut -d= -f2; }

cmd_status() {
  if [ -f "$LEASE" ]; then
    echo "lease: expires $(date -d @"$(lease_get expires)" '+%F %T') ($(( $(lease_get expires) - $(date +%s) ))s left)"
  else
    echo "lease: none"
  fi
  for n in "${NODES[@]}"; do
    if ip netns list | grep -q "^$n\b"; then echo "node $n: up"; else echo "node $n: down"; fi
  done
  if ip netns list | grep -q '^dg-sc\b'; then
    ns dg-sc vtysh -N sc -c 'show bgp summary' 2>/dev/null | sed -n '/Neighbor/,$p'
  fi
}

cmd_extend() {
  need_root; [ -f "$LEASE" ] || die "no lease"
  local add; add="$(to_seconds "${1:?duration}")"
  local exp; exp=$(( $(lease_get expires) + add ))
  printf 'created=%s\nexpires=%s\n' "$(lease_get created)" "$exp" > "$LEASE"
  echo "lease extended to $(date -d @"$exp" '+%F %T')"
}

cmd_reap() {
  need_root
  # No lease but lab nodes exist = default is death.
  if [ ! -f "$LEASE" ]; then
    if ip netns list | grep -q '^dg-'; then echo "reap: nodes without a lease"; cmd_down; fi
    return 0
  fi
  if [ "$(date +%s)" -ge "$(lease_get expires)" ]; then echo "reap: lease expired"; cmd_down; fi
}

case "${1:-}" in
  up) shift; cmd_up "$@" ;;
  down) cmd_down ;;
  status) cmd_status ;;
  extend) shift; cmd_extend "$@" ;;
  reap) cmd_reap ;;
  *) sed -n '2,9p' "$0"; exit 2 ;;
esac
