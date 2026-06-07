#!/usr/bin/env bash
# Daily autonomous radar: scrape → detect → diff → report.
# State file output_reports/.radar_state.json prevents re-generating PDFs
# for unchanged clusters. Only new clusters, score changes >=5, or new
# insiders trigger PDF generation.
#
# Usage: bash scripts/run_daily_radar.sh
# Cron:  0 6 * * 1-5 cd /path/to/bist-flow-intel && bash scripts/run_daily_radar.sh

set -euo pipefail
cd "$(dirname "$0")/.."

DATE=$(date +%Y-%m-%d)
STATE="output_reports/.radar_state.json"
MONLOG="output_reports/monitoring_log.md"

mkdir -p "output_reports/${DATE}"

# Monitoring log'a bir satir ekler
_log_run() {
  local run_date="$1" durum="$2" tickers="$3"
  local cluster_count
  cluster_count=$(python -c "import json,sys; d=json.load(open('${STATE}')); print(len(d.get('clusters',{})))" 2>/dev/null || echo "?")
  if [ ! -f "${MONLOG}" ]; then
    printf "# Radar Monitoring Log\n\n| Tarih | Cluster | Durum | Ticker'lar |\n|---|---|---|---|\n" > "${MONLOG}"
  fi
  printf "| %s | %s | %s | %s |\n" "${run_date}" "${cluster_count}" "${durum}" "${tickers:--}" >> "${MONLOG}"
}

echo "[radar] ${DATE} - scrape (last 72h)"
uv run flow-intel scrape kap-insider --last-hours 72

echo "[radar] ${DATE} - signal detect"
uv run flow-intel signal detect

echo "[radar] ${DATE} - checking for new/changed anomalies"
TICKERS=$(uv run python scripts/radar_diff.py --state "${STATE}" 2>/dev/null || true)

if [ -z "${TICKERS}" ]; then
  echo "[radar] ${DATE} - no new anomalies, skipping PDF generation"
  _log_run "${DATE}" "degisim yok" ""
  exit 0
fi

echo "[radar] ${DATE} - changed tickers: ${TICKERS}"
for T in ${TICKERS}; do
  echo "[radar] ${DATE} - generating report: ${T}"
  uv run flow-intel report generate --ticker "${T}" --output pdf
done

# Reports land in reports/forensic/ (flow-intel default) - copy to dated dir
if ls reports/forensic/"${DATE}"_*.pdf 2>/dev/null | head -1 | grep -q .; then
  cp reports/forensic/"${DATE}"_*.pdf "output_reports/${DATE}/" 2>/dev/null || true
fi

_log_run "${DATE}" "PDF basıldı" "${TICKERS}"
echo "[radar] ${DATE} - done"
