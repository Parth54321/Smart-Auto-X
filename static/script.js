// ============================================================
// script.js  –  Frontend JavaScript for the Dashboard
// ============================================================
//
// PURPOSE:
//   Handles all browser-side interactions:
//     1. Vehicle selection (index.html) → calls /api/select
//     2. START button → calls /api/start
//     3. STOP  button → calls /api/stop
//     4. OVERTAKE button → calls /api/overtake
//     5. Status polling → calls /api/status every 1 second
//     6. Log polling   → calls /api/logs every 1 second
//     7. Updates dashboard UI with latest data
//
// BEGINNER TIP:
//   fetch() is JavaScript's way to make HTTP requests.
//   It works like requests.get() in Python.
// ============================================================


// ─────────────────────────────────────────────────────────────
// HOMEPAGE FUNCTION: selectVehicle()
// Called when user clicks CAR or TRUCK card on index.html
// ─────────────────────────────────────────────────────────────
function selectVehicle(vehicleType) {
    console.log(`[SELECT] Vehicle selected: ${vehicleType}`);

    // Visually highlight the chosen card
    const allCards = document.querySelectorAll('.vehicle-card');
    allCards.forEach(card => card.style.opacity = '0.4');

    const selectedCard = document.getElementById(
        vehicleType === 'CAR' ? 'carCard' : 'truckCard'
    );
    if (selectedCard) {
        selectedCard.style.opacity = '1';
        selectedCard.style.transform = 'scale(1.05)';
    }

    // Step 1: Tell the Flask backend which vehicle was selected
    fetch('/api/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vehicle: vehicleType })
    })
    .then(response => response.json())
    .then(data => {
        console.log(`[SELECT] Server confirmed: ${data.vehicle}`);

        // Step 2: Redirect to the dashboard page
        // Pass the vehicle name as a URL query parameter
        window.location.href = `/dashboard?vehicle=${vehicleType}`;
    })
    .catch(error => {
        console.error('[SELECT ERROR]', error);
        alert('Could not connect to the server. Is Flask running?');
    });
}


// ─────────────────────────────────────────────────────────────
// DASHBOARD FUNCTIONS
// These only run when we are on dashboard.html
// ─────────────────────────────────────────────────────────────

// ── Start System ───────────────────────────────────────────
function startSystem() {
    console.log('[BTN] START pressed');

    // Disable start, enable stop + overtake
    setButtonState(false, true, true);

    fetch('/api/start', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
        console.log('[START]', data);
        if (data.status === 'already running') {
            alert('System is already running!');
        }
    })
    .catch(err => {
        console.error('[START ERROR]', err);
        setButtonState(true, false, false);   // reset buttons on error
    });
}

// ── Stop System ────────────────────────────────────────────
function stopSystem() {
    console.log('[BTN] STOP pressed');

    fetch('/api/stop', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
        console.log('[STOP]', data);
        setButtonState(true, false, false);   // re-enable START
    })
    .catch(err => console.error('[STOP ERROR]', err));
}

// ── Overtake ────────────────────────────────────────────────
function sendOvertake() {
    console.log('[BTN] OVERTAKE pressed');

    // Flash the overtake button
    const btn = document.getElementById('overtakeBtn');
    if (btn) {
        btn.style.transform = 'scale(0.96)';
        setTimeout(() => btn.style.transform = '', 150);
    }

    // Sends POST to Flask → Flask forwards to ESP32-WROOM:
    // http://<ESP32_WROOM_IP>/OVERTAKE
    fetch('/api/overtake', { method: 'POST' })
    .then(r => r.json())
    .then(data => console.log('[OVERTAKE]', data))
    .catch(err => console.error('[OVERTAKE ERROR]', err));
}

// ── Clear logs ──────────────────────────────────────────────
function clearLogs() {
    const logBox = document.getElementById('logBox');
    if (logBox) {
        logBox.innerHTML = '';
    }
    // Reset tracking index so new logs still appear
    lastLogCount = 0;
}


// ─────────────────────────────────────────────────────────────
// Helper: Enable/Disable Control Buttons
// ─────────────────────────────────────────────────────────────
function setButtonState(startEnabled, stopEnabled, overtakeEnabled) {
    const startBtn    = document.getElementById('startBtn');
    const stopBtn     = document.getElementById('stopBtn');
    const overtakeBtn = document.getElementById('overtakeBtn');

    if (startBtn)    startBtn.disabled    = !startEnabled;
    if (stopBtn)     stopBtn.disabled     = !stopEnabled;
    if (overtakeBtn) overtakeBtn.disabled = !overtakeEnabled;
}


// ─────────────────────────────────────────────────────────────
// Status Polling – updates the dashboard cards every second
// Calls GET /api/status
// ─────────────────────────────────────────────────────────────
function pollStatus() {
    fetch('/api/status')
    .then(r => r.json())
    .then(data => {
        updateStatusCards(data);
    })
    .catch(err => {
        // Server might be busy, silently skip
    });
}

function updateStatusCards(data) {
    // ── Running state ──────────────────────────────────────
    const runningVal  = document.getElementById('runningValue');
    const statusDot   = document.getElementById('statusDot');
    const statusLabel = document.getElementById('statusLabel');

    if (runningVal) {
        if (data.running) {
            runningVal.textContent = 'RUNNING';
            runningVal.className   = 'card-value state-running glow-text';
        } else {
            runningVal.textContent = 'STOPPED';
            runningVal.className   = 'card-value state-stopped';
        }
    }

    if (statusDot && statusLabel) {
        if (data.running) {
            statusDot.classList.add('running');
            statusLabel.textContent = 'LIVE';
            statusLabel.classList.add('running');
        } else {
            statusDot.classList.remove('running');
            statusLabel.textContent = 'OFFLINE';
            statusLabel.classList.remove('running');
        }
    }

    // ── Current Lane ───────────────────────────────────────
    const laneVal = document.getElementById('laneValue');
    if (laneVal && data.lane) {
        laneVal.textContent = data.lane;

        // Apply colour class based on lane
        const classMap = {
            'LEFT':    'card-value lane-left',
            'MIDDLE':  'card-value lane-middle',
            'RIGHT':   'card-value lane-right',
            'UNKNOWN': 'card-value',
        };
        laneVal.className = classMap[data.lane] || 'card-value';
    }

    // ── Current Direction (command) ────────────────────────
    const dirVal = document.getElementById('dirValue');
    if (dirVal && data.command) {
        const arrows = {
            'FORWARD':  '↑ FORWARD',
            'LEFT':     '← LEFT',
            'RIGHT':    '→ RIGHT',
            'STOP':     '■ STOP',
            'OVERTAKE': '⚡ OVERTAKE',
            'NONE':     '—',
        };
        dirVal.textContent = arrows[data.command] || data.command;
    }

    // ── Sync button state with running status ──────────────
    if (data.running) {
        setButtonState(false, true, true);
    } else {
        setButtonState(true, false, false);
    }
}


// ─────────────────────────────────────────────────────────────
// Log Polling – fetches new log entries every second
// Calls GET /api/logs
// ─────────────────────────────────────────────────────────────
let lastLogCount = 0;   // tracks how many logs we've already shown

function pollLogs() {
    fetch('/api/logs')
    .then(r => r.json())
    .then(data => {
        if (data.logs && data.logs.length > lastLogCount) {
            // Only add the NEW entries we haven't shown yet
            const newEntries = data.logs.slice(lastLogCount);
            newEntries.forEach(entry => appendLogEntry(entry));
            lastLogCount = data.logs.length;
        }
    })
    .catch(err => {
        // Silently fail – server may be busy
    });
}

function appendLogEntry(entry) {
    const logBox = document.getElementById('logBox');
    if (!logBox) return;

    // Remove the "Waiting..." placeholder on first real log
    if (lastLogCount === 1) {
        logBox.innerHTML = '';
    }

    // Create a new log entry div
    const div = document.createElement('div');

    // Choose CSS class based on log type
    const classMap = {
        'INFO':    'log-entry log-info',
        'COMMAND': 'log-entry log-command',
        'WARN':    'log-entry log-warn',
        'ERROR':   'log-entry log-error',
    };
    div.className = classMap[entry.type] || 'log-entry log-info';

    // Build inner HTML
    div.innerHTML = `
        <span class="log-time">${entry.time || '--:--:--'}</span>
        <span class="log-tag">[${entry.type}]</span>
        <span class="log-msg">${entry.msg}</span>
    `;

    // Add to the log box
    logBox.appendChild(div);

    // Auto-scroll to the newest entry
    logBox.scrollTop = logBox.scrollHeight;

    // Keep log box from getting too long (max 80 visible entries)
    const entries = logBox.querySelectorAll('.log-entry');
    if (entries.length > 80) {
        entries[0].remove();
    }
}


// ─────────────────────────────────────────────────────────────
// Auto-start polling when on the dashboard page
// ─────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {

    // Only poll if we are on the dashboard (check for logBox)
    const logBox = document.getElementById('logBox');
    if (!logBox) return;    // not on dashboard, skip polling

    console.log('[DASHBOARD] Polling started...');

    // Poll status and logs every 1000 ms (1 second)
    setInterval(pollStatus, 1000);
    setInterval(pollLogs,   1000);

    // Initial poll immediately
    pollStatus();
    pollLogs();
});
