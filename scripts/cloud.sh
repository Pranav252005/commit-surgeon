#!/usr/bin/env bash
# Run the ScopeBench model evals on a GitHub Codespace (CPU only, free student hours) instead of this machine.
#   scripts/cloud.sh up                  create or start the Codespace, make sure Ollama is installed and serving
#   scripts/cloud.sh speed [model]       tokens/s of one model on the Codespace's CPU: measure before a long run
#   scripts/cloud.sh run [model ...]     copy the code, run bench/leaderboard.sh there, wait, pull results, stop the Codespace
#   scripts/cloud.sh status | pull | down
# Same pattern as Cuemo's `cloud up|down|status` (VTalk/packages/stream/src/cloud.ts): `gh codespace`, the code copied as a
# tarball over ssh, the machine stopped when done so it stops using the free hours. Needs `gh` signed in with the codespace scope.
# MAX_HUNKS (default 40) is passed through to leaderboard.sh. Results are resumable, so a stopped run just continues.
set -u
cd "$(dirname "$0")/.."
REPO="${SURGEON_CLOUD_REPO:-$(git remote get-url origin 2>/dev/null | sed -E 's#^(https://github.com/|git@github.com:)##; s#\.git$##')}"
NAME="surgeon-bench"
MACHINE="${SURGEON_CLOUD_MACHINE:-standardLinux32gb}"  # 4 cores, 16 GB
die() { echo "cloud: $*" >&2; exit 1; }
[ -n "$REPO" ] || die "no GitHub repo: set SURGEON_CLOUD_REPO=owner/name (the Codespace is created from it)"

cs_name() { gh codespace list -R "$REPO" --json name,displayName --jq ".[] | select(.displayName==\"$NAME\") | .name"; }
remote() { gh codespace ssh -c "$CS" -- "$@"; }

up() {
  CS="$(cs_name)" || die "gh codespace list failed (gh auth refresh -h github.com -s codespace)"
  if [ -z "$CS" ]; then
    echo "cloud: creating the Codespace (first time, a few minutes)..."
    gh codespace create -R "$REPO" -b main -m "$MACHINE" --idle-timeout 60m --display-name "$NAME" || die "could not create it"
    CS="$(cs_name)"
  fi
  [ -n "$CS" ] || die "the Codespace was created but cannot be found"
  echo "cloud: $CS, connecting (a stopped machine starts now)..."
  remote 'echo ready' | grep -q ready || die "cannot open a shell (does .devcontainer have the sshd feature, and is it pushed to $REPO?)"
  remote 'command -v ollama >/dev/null || { sudo apt-get install -y -qq zstd && curl -fsSL https://ollama.com/install.sh | sh; }
          command -v uv >/dev/null || pip install -q --no-cache-dir uv
          curl -fs localhost:11434/api/version >/dev/null || { setsid nohup ollama serve >/tmp/ollama.log 2>&1 & }
          for i in $(seq 30); do curl -fs localhost:11434/api/version >/dev/null && exit 0; sleep 1; done; exit 1' || die "ollama does not answer"
  echo "cloud: ready"
}

sync() {
  echo "cloud: copying the code..."
  tar czf - --exclude=.git --exclude=.venv --exclude=__pycache__ --exclude=.surgeon-cache --exclude=.pytest_cache \
    --exclude=.ruff_cache --exclude=PLAN.md . | remote 'mkdir -p $HOME/surgeon && tar xzf - -C $HOME/surgeon' || die "copy failed"
}

pull() {
  [ -n "${CS:-}" ] || CS="$(cs_name)"; [ -n "$CS" ] || die "no Codespace"
  local bak=".surgeon-cache/results-before-pull-$(date +%s)"
  mkdir -p "$bak" && cp -r bench/results "$bak"/ && echo "cloud: old results saved in $bak"
  remote 'cd $HOME/surgeon/bench && tar czf - results RESULTS.md LEADERBOARD.md leaderboard.json 2>/dev/null' | tar xzf - -C bench || die "pull failed"
  echo "cloud: results are in bench/ (git status shows what changed)"
}

down() {
  CS="$(cs_name)"; [ -n "$CS" ] || { echo "cloud: nothing to stop"; return 0; }
  gh codespace stop -c "$CS" && echo "cloud: $CS stopped"
}

case "${1:-}" in
  up) up ;;
  speed)
    up; m="${2:-gemma3:4b}"
    remote "ollama pull $m >/dev/null 2>&1; ollama run $m --verbose 'Explain in two sentences what a git rebase does.' 2>&1 | grep -E 'eval rate'" ;;
  run)
    shift; models=("$@"); [ ${#models[@]} -eq 0 ] && models=(gemma3:4b gemma3:1b llama3.2:3b)
    up; sync
    remote '[ -f $HOME/surgeon/run.pid ] && kill -0 "$(cat $HOME/surgeon/run.pid)" 2>/dev/null' && die "a run is already going; use status / pull / down"
    gh auth token | remote 'umask 077; cat > $HOME/.gh_token'  # for GitHub API reads; deleted when the run ends
    { printf '#!/usr/bin/env bash\ncd "$HOME/surgeon" || exit 1\necho $$ > run.pid; rm -f run.done\n'
      printf 'export GITHUB_TOKEN="$(cat "$HOME/.gh_token")" MAX_HUNKS=%q\n' "${MAX_HUNKS:-40}"
      printf 'bench/leaderboard.sh'; printf ' %q' "${models[@]}"; printf ' > run.log 2>&1\necho $? > run.done\nrm -f "$HOME/.gh_token" run.pid\n'
    } | remote 'cat > $HOME/surgeon/.run.sh && chmod +x $HOME/surgeon/.run.sh && cd $HOME/surgeon && chmod +x bench/leaderboard.sh && { setsid nohup ./.run.sh >/dev/null 2>&1 & }'
    echo "cloud: running ${models[*]} (Ctrl+C only stops watching; the Codespace stops by itself after 60 idle minutes)"
    trap 'echo; echo "cloud: still running. scripts/cloud.sh status | pull | down"; exit 0' INT
    while ! remote 'test -f $HOME/surgeon/run.done' 2>/dev/null; do
      remote 'tail -n 1 $HOME/surgeon/run.log' 2>/dev/null || echo "(waiting for the Codespace)"
      sleep 60
    done
    pull; down ;;
  status)
    CS="$(cs_name)"; [ -n "$CS" ] || die "no Codespace yet"
    gh codespace list -R "$REPO" --json displayName,state --jq ".[] | select(.displayName==\"$NAME\") | .state"
    remote 'cd $HOME/surgeon 2>/dev/null && { test -f run.done && echo "finished, exit $(cat run.done)"; tail -n 3 run.log; }' 2>/dev/null ;;
  pull) pull ;;
  down) down ;;
  *) sed -n 2,6p "$0"; exit 2 ;;
esac
