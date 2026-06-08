#!/usr/bin/env bash
# tool-calling spike 复现 harness（第 0 步 · 最大风险点）。
# 一键：preflight → 起 PilotDeck server(自管生命周期) → 批量跑「读文件→总结→写回」→ 统计成功率 → 落日志。
# 验证的是：本地模型经 PilotDeck agent loop 能否稳定走【原生 tool_calls】完成多步工具任务。
#
# 用法:
#   bash run.sh [N]            # 跑 N 次(默认 8)
#   N=20 bash run.sh           # 同上
#   KEEP_SERVER=1 bash run.sh  # 跑完不关 server(连续调试用)
#   bash run.sh --stop         # 只停掉本 harness 起的 server
#
# 约定:
#   - 模型由 deploy/pilot-home/pilotdeck.yaml 的 agent.model 决定(当前 ollama/gpt-oss:20b)，本脚本不改模型。
#   - agent 工作根 = 本目录下 workspace/(已 git init，确保 agent 读写只落在这里，不脏 submodule/仓库)。
#   - 教训内置：用普通文件名(非点目录)、每次唯一 session id —— 避免路径被模型篡改 / 会话记忆残留。
set -euo pipefail

SPIKE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SPIKE_DIR/../../.." && pwd)"
PILOTDECK="$REPO_ROOT/vendor/pilotdeck"
TSX="$PILOTDECK/node_modules/.bin/tsx"
CLI="$PILOTDECK/src/cli/pilotdeck.ts"

export PILOT_HOME="${PILOT_HOME:-$REPO_ROOT/deploy/pilot-home}"
export PILOTDECK_GATEWAY_PORT="${PILOTDECK_GATEWAY_PORT:-18790}"
API_PORT="${API_PORT:-8642}"
API="http://127.0.0.1:${API_PORT}"
OLLAMA="${OLLAMA:-http://localhost:11434}"

WORKSPACE="$SPIKE_DIR/workspace"
RESULTS="$SPIKE_DIR/results"
LOG="$RESULTS/server.log"
PIDFILE="$RESULTS/server.pid"

log() { printf '\033[36m[harness]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[harness] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# PIDFILE 存的是 server 进程组的 PGID(= setsid 出来的 leader pid)。
# 用 `kill -- -PGID` 杀整组：tsx wrapper + 真正的 node 子进程 + agent 拉起的 playwright-mcp 全清，避免孤儿占端口。
stop_server() {
  if [ -f "$PIDFILE" ]; then
    pgid="$(cat "$PIDFILE")"
    if [ -n "$pgid" ] && kill -0 "$pgid" 2>/dev/null; then
      log "停止 harness server 进程组 (pgid $pgid)"
      kill -TERM -- "-$pgid" 2>/dev/null || true
      sleep 2
      kill -KILL -- "-$pgid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
  fi
}
trap 'stop_server' INT TERM

if [ "${1:-}" = "--stop" ]; then stop_server; exit 0; fi

N="${1:-${N:-8}}"
mkdir -p "$WORKSPACE" "$RESULTS"
# workspace 必须自己是 git 根，否则 PilotDeck 会向上找到外层仓库当项目根 → 写到仓库根。
[ -d "$WORKSPACE/.git" ] || git init -q "$WORKSPACE"

# --- 1. preflight ---
log "preflight: ollama @ $OLLAMA"
curl -fsS "$OLLAMA/v1/models" >/dev/null 2>&1 || die "ollama 不可达 ($OLLAMA)。先 ollama serve。"
[ -x "$TSX" ] || die "找不到 tsx：$TSX。先在 $PILOTDECK 跑 pnpm install。"

# --- 2. 起 server(若 harness 自己的没在跑) ---
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  log "复用已在跑的 harness server (pid $(cat "$PIDFILE"))"
elif curl -fsS "$API/health" >/dev/null 2>&1; then
  die "端口 $API_PORT 已被别的 server 占用(非本 harness 起的)。先停掉它，或设 API_PORT=别的端口。"
else
  log "启动 PilotDeck server (cwd=workspace, gateway:$PILOTDECK_GATEWAY_PORT, api:$API_PORT)"
  # setsid 让 server 成为独立进程组 leader；$! 即 PGID，停服时按组杀(连同 node 子进程 + playwright-mcp)。
  setsid bash -c "cd '$WORKSPACE' && exec '$TSX' '$CLI' server" >"$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 60); do
    curl -fsS "$API/health" >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS "$API/health" >/dev/null 2>&1 || { tail -20 "$LOG"; die "server 起不来，见 $LOG"; }
  log "server 就绪 (pid $(cat "$PIDFILE"))，日志 $LOG"
fi

# --- 3. 批量跑 ---
cp "$SPIKE_DIR/fixtures/source.txt" "$WORKSPACE/source.txt"
rm -f "$WORKSPACE"/out_*.txt
RUNID="$(date +%s)"
PASS=0 ; GROUNDED=0 ; TOTAL_S=0
log "开始批量 $N 次（读 source.txt → 一句中文总结 → 写 out_N.txt）"
for i in $(seq 1 "$N"); do
  prompt="请用文件工具：读取 source.txt，用一句中文总结其内容，写入 out_${i}.txt。完成后回复 done。"
  body=$(MSG="$prompt" python3 -c 'import json,os;print(json.dumps({"model":"pilotdeck-gateway","stream":False,"messages":[{"role":"user","content":os.environ["MSG"]}]}))')
  t0=$(date +%s)
  curl -s -X POST "$API/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -H "X-Hermes-Session-Id: run-$RUNID-$i" \
    -d "$body" --max-time 300 > "$RESULTS/resp_$i.json" || true
  dt=$(( $(date +%s) - t0 )); TOTAL_S=$((TOTAL_S+dt))
  out="$WORKSPACE/out_$i.txt"
  if [ -s "$out" ]; then
    PASS=$((PASS+1)); cp "$out" "$RESULTS/out_$i.txt"
    grounded=""
    if grep -qiE "PilotDeck|ollama|tool" "$out"; then GROUNDED=$((GROUNDED+1)); grounded=" grounded"; fi
    printf '  run %2d: \033[32mPASS\033[0m %4sB %3ss%s\n' "$i" "$(wc -c <"$out")" "$dt" "$grounded"
  else
    snippet=$(python3 -c "import json,sys;print(json.load(open('$RESULTS/resp_$i.json'))['choices'][0]['message']['content'][:120].replace(chr(10),' '))" 2>/dev/null || echo "(no/invalid resp)")
    printf '  run %2d: \033[31mFAIL\033[0m %3ss reply=%s\n' "$i" "$dt" "$snippet"
  fi
done

avg=$(( N>0 ? TOTAL_S/N : 0 ))
echo "------------------------------------------------------------"
printf '结果: \033[1m%d/%d 通过\033[0m  (内容扣题 %d/%d)  平均 %ss/次\n' "$PASS" "$N" "$GROUNDED" "$N" "$avg"
echo "输出与响应留样: $RESULTS/  (out_*.txt / resp_*.json)；server 日志: $LOG"

if [ "${KEEP_SERVER:-0}" != "1" ]; then stop_server; log "已停 server（KEEP_SERVER=1 可保留）。"; fi
