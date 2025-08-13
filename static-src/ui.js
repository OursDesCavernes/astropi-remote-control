const log = document.getElementById('status-log');
const statusCurrent = document.getElementById('status-current');
const stopBtn = document.getElementById('stop-btn');
const bulbContainer = document.getElementById('bulb-input-container');
const bulbInput = document.getElementById('bulb-duration');
const systemActions = document.getElementById('system-actions');

function addToLog(message) {
    const p = document.createElement('p');
    p.textContent = `> ${message}`;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
}

async function fetchCameraConfig(selectElement) {
    const configName = selectElement.dataset.config;
    addToLog(`Fetching settings for ${configName}...`);
    try {
        const response = await fetch(`/api/config/${configName}`);
        const data = await response.json();
        if (data.error) {
            addToLog(`Error for ${configName}: ${data.error}`);
            selectElement.innerHTML = `<option>${data.error}</option>`;
            return;
        }

        selectElement.innerHTML = ''; // Clear loading message
        data.choices.forEach(choice => {
            const option = document.createElement('option');
            option.value = choice.value;
            option.textContent = choice.value;
            selectElement.appendChild(option);
        });

        selectElement.value = data.current;
        addToLog(`Loaded ${configName}. Current: ${data.current}`);

        // Special handling for shutter speed bulb mode
        if (configName === 'shutter-speed') {
            handleShutterChange();
        }

    } catch (error) {
        addToLog(`Failed to fetch ${configName} settings: ${error}`);
        selectElement.innerHTML = `<option>Error loading</option>`;
    }
}

async function setCameraConfig(configName, value) {
    addToLog(`Setting ${configName} to: ${value}`);
    try {
        const response = await fetch(`/api/config/${configName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: value })
        });
        const data = await response.json();
        if (data.status !== 'success') {
            addToLog(`Failed to set ${configName}: ${data.message}`);
        }
    } catch (error) {
        addToLog(`Error setting ${configName}: ${error}`);
    }
}

function handleShutterChange() {
    const shutterSelect = document.getElementById('shutter-speed-select');
    if (shutterSelect.value.toLowerCase() === 'bulb') {
        bulbContainer.classList.remove('hidden');
    } else {
        bulbContainer.classList.add('hidden');
    }
}

function getExposureValue() {
    const shutterSelect = document.getElementById('shutter-speed-select');
    const selectedValue = shutterSelect.value;
    if (selectedValue.toLowerCase() === 'bulb') {
        return bulbInput.value;
    }
    try {
        // Handles fractions like "1/100"
        return eval(selectedValue);
    } catch {
        return selectedValue;
    }
}

async function submitCapture(type, params) {
    addToLog(`Starting ${type} capture...`);
    stopBtn.classList.remove('hidden');
    try {
        const response = await fetch('/start_capture', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, ...params })
        });
        const data = await response.json();
        if (data.status === 'error') {
             addToLog(`Error: ${data.message}`);
             stopBtn.classList.add('hidden');
        } else {
             addToLog(data.message);
             checkStatus();
        }
    } catch (error) {
        addToLog(`Network or server error: ${error}`);
        stopBtn.classList.add('hidden');
    }
}

async function checkStatus() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        if (data.status === 'capturing') {
            statusCurrent.textContent = data.message;
            setTimeout(checkStatus, 2000);
        } else {
            statusCurrent.textContent = data.message;
            addToLog(`Finished: ${data.message}`);
            stopBtn.classList.add('hidden');
        }
    } catch (error) {
        addToLog(`Status check failed: ${error}`);
        stopBtn.classList.add('hidden');
    }
}

async function fetchSystemManagement() {
    addToLog(`Fetching system options ...`);
    try {
        const response = await fetch(`/api/system`);
        const data = await response.json();
        if (data.error) {
            addToLog(`Error for ${configName}: ${data.error}`);
            systemActions.innerHTML = `<option>${data.error}</option>`;
            return;
        }

        systemActions.innerHTML = ''; // Clear loading message
        data.choices.forEach(choice => {
            const action = document.createElement('button');
            action.id = `${choice}-btn`;
            action.innerHTML = choice;
            action.textContent = choice;
            action.className = "w-full mt-4 btn-danger text-white font-bold py-2 px-4 rounded"
            action.addEventListener(
                'click', async () => {
                    addToLog(`Sending ${choice} request...`);
                    try {
                        const r = await fetch(`/api/system`,{
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ action: choice })
                            });
                        addToLog((await r.json()).message);
                    } catch (err) {
                        addToLog(`Error stopping: ${err}`);
                    }
                }
            );
            systemActions.appendChild(action);
        });

    } catch (error) {
        addToLog(`Failed to fetch system actions: ${error}`);
        systemActions.innerHTML = `<option>Error loading</option>`;
    }
}

// --- Event Listeners ---
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.camera-config-select').forEach(fetchCameraConfig);
    fetchSystemManagement();
});

document.body.addEventListener('change', (event) => {
    if (event.target.matches('.camera-config-select')) {
        const configName = event.target.dataset.config;
        const value = event.target.value;
        setCameraConfig(configName, value);
        if (configName === 'shutter-speed') {
            handleShutterChange();
        }
        if (configName === 'manual-focus') {
            event.target.value = "0";
        }
    }
});

document.getElementById('lights-form').addEventListener(
    'submit',
    (e) => {
        e.preventDefault();
        submitCapture(
            'lights',
            {
                exposure: getExposureValue(),
                count: document.getElementById('lights-count').value
            }
        );
    }
);
document.getElementById('darks-form').addEventListener(
    'submit',
    (e) => {
        e.preventDefault();
        submitCapture(
            'darks', {
                exposure: getExposureValue(),
                count: document.getElementById('darks-count').value
            }
        );
    }
);
document.getElementById('offsets-form').addEventListener(
    'submit',
    (e) => {
        e.preventDefault();
        submitCapture(
            'offsets', {
                exposure: getExposureValue(),
                count: document.getElementById('offsets-count').value
                }
            );
        }
    );
stopBtn.addEventListener(
    'click', async () => {
        addToLog('Sending stop request...');
        try {
            const r = await fetch('/stop_capture', { method: 'POST' });
            addToLog((await r.json()).message);
        } catch (err) {
            addToLog(`Error stopping: ${err}`);
        }
        stopBtn.classList.add('hidden');
    }
);