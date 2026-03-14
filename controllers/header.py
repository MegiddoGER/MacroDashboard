"""
controllers/header.py — Top-Metriken und Börsen-Uhren.
"""

import streamlit as st
import streamlit.components.v1 as components
from services.cache import cached_quote


def display_header():
    """Zeigt die Top-3-Metriken (S&P 500, Gold, Dollar Index)."""
    cols = st.columns(3)
    metrics = [
        ("S&P 500 Futures", "ES=F"),
        ("Gold", "GC=F"),
        ("US Dollar Index", "DX-Y.NYB"),
    ]
    for col, (label, ticker) in zip(cols, metrics):
        q = cached_quote(ticker)
        with col:
            if q:
                st.metric(
                    label=label,
                    value=f"{q['price']:,.2f} €",
                    delta=f"{q['change_pct']:+.2f} %",
                )
            else:
                st.metric(label=label, value="—", delta="n/a")
            st.markdown(
                "<div style='text-align: left; font-size: 0.65rem; color: #64748b; margin-top: -12px; margin-bottom: 8px; margin-left: 2px;'>Tagesveränderung</div>",
                unsafe_allow_html=True
            )


def display_market_clocks():
    """Rendert die Börsen-Uhren (Xetra + NASDAQ) als HTML-Widget."""
    components.html("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', sans-serif; }
        body { background: transparent; }
    </style>
    <div style="display: flex; gap: 16px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 280px; background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148, 163, 184, 0.12); border-radius: 12px; padding: 16px 20px; backdrop-filter: blur(8px);">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                <span style="font-size:1.3rem;">&#127465;&#127466;</span>
                <span style="color:#e2e8f0; font-weight:600; font-size:0.95rem;">Deutsche Börse (Xetra)</span>
                <span id="xetra-status" style="margin-left:auto; padding:2px 10px; border-radius:20px; font-size:0.7rem; font-weight:600; letter-spacing:0.05em;"></span>
            </div>
            <div style="display:flex; align-items:baseline; gap:12px;">
                <span id="de-time" style="color:#e2e8f0; font-size:1.5rem; font-weight:700; font-variant-numeric:tabular-nums;"></span>
                <span style="color:#64748b; font-size:0.75rem;">MEZ</span>
            </div>
            <div style="margin-top:8px; display:flex; align-items:center; gap:8px;">
                <span style="color:#64748b; font-size:0.75rem;">Handelszeiten: 09:00 – 17:30</span>
            </div>
            <div style="margin-top:6px; display:flex; align-items:center; gap:6px;">
                <span id="xetra-countdown-label" style="color:#94a3b8; font-size:0.78rem;"></span>
                <span id="xetra-countdown" style="color:#00d4aa; font-size:0.95rem; font-weight:600; font-variant-numeric:tabular-nums;"></span>
            </div>
        </div>
        <div style="flex: 1; min-width: 280px; background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148, 163, 184, 0.12); border-radius: 12px; padding: 16px 20px; backdrop-filter: blur(8px);">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                <span style="font-size:1.3rem;">&#127482;&#127480;</span>
                <span style="color:#e2e8f0; font-weight:600; font-size:0.95rem;">NASDAQ (New York)</span>
                <span id="nasdaq-status" style="margin-left:auto; padding:2px 10px; border-radius:20px; font-size:0.7rem; font-weight:600; letter-spacing:0.05em;"></span>
            </div>
            <div style="display:flex; align-items:baseline; gap:12px;">
                <span id="ny-time" style="color:#e2e8f0; font-size:1.5rem; font-weight:700; font-variant-numeric:tabular-nums;"></span>
                <span style="color:#64748b; font-size:0.75rem;">ET</span>
            </div>
            <div style="margin-top:8px; display:flex; align-items:center; gap:8px;">
                <span style="color:#64748b; font-size:0.75rem;">Handelszeiten: 09:30 – 16:00</span>
            </div>
            <div style="margin-top:6px; display:flex; align-items:center; gap:6px;">
                <span id="nasdaq-countdown-label" style="color:#94a3b8; font-size:0.78rem;"></span>
                <span id="nasdaq-countdown" style="color:#00d4aa; font-size:0.95rem; font-weight:600; font-variant-numeric:tabular-nums;"></span>
            </div>
        </div>
    </div>
    <script>
    (function() {
        function pad(n) { return n < 10 ? '0' + n : '' + n; }
        function formatCountdown(ms) {
            if (ms <= 0) return '00:00:00';
            var totalSec = Math.floor(ms / 1000);
            var h = Math.floor(totalSec / 3600);
            var m = Math.floor((totalSec % 3600) / 60);
            var s = totalSec % 60;
            return pad(h) + ':' + pad(m) + ':' + pad(s);
        }
        function getTimeInTZ(tzName) {
            var now = new Date();
            return now.toLocaleString('de-DE', {timeZone: tzName, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'});
        }
        function getDayInTZ(tzName) {
            var now = new Date();
            return now.toLocaleString('en-US', {timeZone: tzName, weekday: 'short'});
        }
        function getMinutesSinceMidnight(tzName) {
            var now = new Date();
            var parts = now.toLocaleString('en-US', {timeZone: tzName, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'}).split(':');
            return parseInt(parts[0]) * 60 + parseInt(parts[1]) + parseInt(parts[2]) / 60;
        }
        function isWeekday(tzName) {
            var d = getDayInTZ(tzName);
            return d !== 'Sat' && d !== 'Sun';
        }
        function getMsUntil(tzName, targetHour, targetMin) {
            var now = new Date();
            var parts = now.toLocaleString('en-US', {timeZone: tzName, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'}).split(':');
            var nowSec = parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60 + parseInt(parts[2]);
            var targetSec = targetHour * 3600 + targetMin * 60;
            var diff = targetSec - nowSec;
            if (diff < 0) diff += 86400;
            return diff * 1000;
        }
        function daysUntilMonday(tzName) {
            var d = getDayInTZ(tzName);
            if (d === 'Sat') return 2;
            if (d === 'Sun') return 1;
            return 0;
        }

        function update() {
            var deTZ = 'Europe/Berlin';
            var deTimeEl = document.getElementById('de-time');
            var xetraStatusEl = document.getElementById('xetra-status');
            var xetraLabelEl = document.getElementById('xetra-countdown-label');
            var xetraCountEl = document.getElementById('xetra-countdown');
            if (!deTimeEl) return;

            deTimeEl.textContent = getTimeInTZ(deTZ);
            var deMin = getMinutesSinceMidnight(deTZ);
            var deWeekday = isWeekday(deTZ);
            var xetraOpen = deWeekday && deMin >= 540 && deMin < 1050;

            if (xetraOpen) {
                xetraStatusEl.textContent = 'OFFEN';
                xetraStatusEl.style.background = 'rgba(34,197,94,0.15)';
                xetraStatusEl.style.color = '#22c55e';
                xetraLabelEl.textContent = 'Schließt in:';
                xetraCountEl.textContent = formatCountdown(getMsUntil(deTZ, 17, 30));
            } else {
                xetraStatusEl.textContent = 'GESCHLOSSEN';
                xetraStatusEl.style.background = 'rgba(239,68,68,0.15)';
                xetraStatusEl.style.color = '#ef4444';
                xetraLabelEl.textContent = 'Öffnet in:';
                var daysToMon = daysUntilMonday(deTZ);
                if (!deWeekday) {
                    var msToMid = getMsUntil(deTZ, 24, 0);
                    xetraCountEl.textContent = formatCountdown(msToMid + (daysToMon - 1) * 86400000 + 9 * 3600000);
                } else if (deMin >= 1050) {
                    var dayName = getDayInTZ(deTZ);
                    var msToMid = getMsUntil(deTZ, 24, 0);
                    if (dayName === 'Fri') {
                        xetraCountEl.textContent = formatCountdown(msToMid + 2 * 86400000 + 9 * 3600000);
                    } else {
                        xetraCountEl.textContent = formatCountdown(msToMid + 9 * 3600000);
                    }
                } else {
                    xetraCountEl.textContent = formatCountdown(getMsUntil(deTZ, 9, 0));
                }
            }

            var nyTZ = 'America/New_York';
            var nyTimeEl = document.getElementById('ny-time');
            var nasdaqStatusEl = document.getElementById('nasdaq-status');
            var nasdaqLabelEl = document.getElementById('nasdaq-countdown-label');
            var nasdaqCountEl = document.getElementById('nasdaq-countdown');
            nyTimeEl.textContent = getTimeInTZ(nyTZ);
            var nyMin = getMinutesSinceMidnight(nyTZ);
            var nyWeekday = isWeekday(nyTZ);
            var nasdaqOpen = nyWeekday && nyMin >= 570 && nyMin < 960;

            if (nasdaqOpen) {
                nasdaqStatusEl.textContent = 'OPEN';
                nasdaqStatusEl.style.background = 'rgba(34,197,94,0.15)';
                nasdaqStatusEl.style.color = '#22c55e';
                nasdaqLabelEl.textContent = 'Schließt in:';
                nasdaqCountEl.textContent = formatCountdown(getMsUntil(nyTZ, 16, 0));
            } else {
                nasdaqStatusEl.textContent = 'CLOSED';
                nasdaqStatusEl.style.background = 'rgba(239,68,68,0.15)';
                nasdaqStatusEl.style.color = '#ef4444';
                nasdaqLabelEl.textContent = 'Öffnet in:';
                var nyDaysToMon = daysUntilMonday(nyTZ);
                if (!nyWeekday) {
                    var msToMid = getMsUntil(nyTZ, 24, 0);
                    nasdaqCountEl.textContent = formatCountdown(msToMid + (nyDaysToMon - 1) * 86400000 + 9.5 * 3600000);
                } else if (nyMin >= 960) {
                    var nyDayName = getDayInTZ(nyTZ);
                    var msToMid = getMsUntil(nyTZ, 24, 0);
                    if (nyDayName === 'Fri') {
                        nasdaqCountEl.textContent = formatCountdown(msToMid + 2 * 86400000 + 9.5 * 3600000);
                    } else {
                        nasdaqCountEl.textContent = formatCountdown(msToMid + 9.5 * 3600000);
                    }
                } else {
                    nasdaqCountEl.textContent = formatCountdown(getMsUntil(nyTZ, 9, 30));
                }
            }
        }
        update();
        setInterval(update, 1000);
    })();
    </script>
    """, height=140, scrolling=False)
