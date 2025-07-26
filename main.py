from flask import Flask, render_template_string, request, jsonify
import subprocess
import os
import signal
import re

app = Flask(__name__)

# --- Global variable to hold the process ---
capture_process = None

# --- Configuration Mapping ---
# Maps simple names to the full gphoto2 config paths.
CONFIG_MAP = {
    'shutterspeed': '/main/capturesettings/shutterspeed',
    'iso': '/main/imgsettings/iso',
    'f-number': '/main/capturesettings/f-number'
}


# --- Helper function for running gphoto2 commands ---
def run_gphoto_command(cmd):
    """Runs a gphoto2 command with a specific LANG environment variable for consistent output."""
    env = os.environ.copy()
    env['LANG'] = 'C.UTF-8'
    try:
        # Using a timeout to prevent the command from hanging indefinitely
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            env=env,
            timeout=10
        )
        return process.stdout, process.stderr
    except subprocess.CalledProcessError as e:
        return e.stdout, e.stderr
    except subprocess.TimeoutExpired:
        return None, "gphoto2 command timed out. Is the camera connected and responsive?"
    except FileNotFoundError:
        return None, "gphoto2 command not found. Is it installed and in your PATH?"


# --- HTML & JavaScript Frontend ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale-1.0">
    <title>AstroPi Control</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .card { background-color: #1f2937; color: #f3f4f6; }
        .btn-primary { background-color: #3b82f6; transition: background-color 0.3s; }
        .btn-primary:hover { background-color: #2563eb; }
        .btn-danger { background-color: #ef4444; transition: background-color: 0.3s; }
        .btn-danger:hover { background-color: #dc2626; }
        .input-field, .select-field { background-color: #374151; border-color: #4b5563; }
        #status-log { background-color: #111827; font-family: 'monospace'; height: 200px; overflow-y: scroll; border: 1px solid #4b5563; }
    </style>
</head>
<body class="bg-gray-900 text-white p-4 md:p-8">
    <div class="max-w-4xl mx-auto">
        <header class="text-center mb-8">
            <h1 class="text-4xl font-bold text-blue-400">AstroPi Camera Control</h1>
            <p class="text-gray-400">Control your astrophotography captures from your browser.</p>
        </header>

        <!-- Global Settings -->
        <div class="card p-6 rounded-lg shadow-lg mb-6">
            <h2 class="text-2xl font-semibold mb-4 text-cyan-400">Camera Settings</h2>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 items-end">
                <div>
                    <label for="iso-select" class="block mb-1 text-sm font-medium">ISO</label>
                    <select id="iso-select" data-config="iso" class="w-full p-2 rounded select-field camera-config-select">
                        <option>Loading...</option>
                    </select>
                </div>
                <div>
                    <label for="f-number-select" class="block mb-1 text-sm font-medium">Aperture (F-Number)</label>
                    <select id="f-number-select" data-config="f-number" class="w-full p-2 rounded select-field camera-config-select">
                        <option>Loading...</option>
                    </select>
                </div>
                <div>
                    <label for="shutter-speed-select" class="block mb-1 text-sm font-medium">Shutter Speed</label>
                    <select id="shutter-speed-select" data-config="shutterspeed" class="w-full p-2 rounded select-field camera-config-select">
                        <option>Loading...</option>
                    </select>
                </div>
            </div>
            <div id="bulb-input-container" class="hidden mt-4">
                <label for="bulb-duration" class="block mb-1 text-sm font-medium">Bulb Duration (s)</label>
                <input type="number" id="bulb-duration" value="60" class="w-full p-2 rounded input-field">
            </div>
        </div>

        <div id="controls" class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <!-- Lights, Darks, Offsets Cards -->
            <div class="card p-6 rounded-lg shadow-lg"><h2 class="text-2xl font-semibold mb-4 text-yellow-400">Lights</h2><form id="lights-form" class="space-y-4"><div><label for="lights-count" class="block mb-1 text-sm font-medium">Number of Shots</label><input type="number" id="lights-count" value="10" class="w-full p-2 rounded input-field"></div><button type="submit" class="w-full btn-primary text-white font-bold py-2 px-4 rounded">Start Lights</button></form></div>
            <div class="card p-6 rounded-lg shadow-lg"><h2 class="text-2xl font-semibold mb-4 text-purple-400">Darks</h2><form id="darks-form" class="space-y-4"><div><label for="darks-count" class="block mb-1 text-sm font-medium">Number of Shots</label><input type="number" id="darks-count" value="10" class="w-full p-2 rounded input-field"></div><button type="submit" class="w-full btn-primary text-white font-bold py-2 px-4 rounded">Start Darks</button></form></div>
            <div class="card p-6 rounded-lg shadow-lg"><h2 class="text-2xl font-semibold mb-4 text-green-400">Offsets/Bias</h2><form id="offsets-form" class="space-y-4"><div><label for="offsets-count" class="block mb-1 text-sm font-medium">Number of Shots</label><input type="number" id="offsets-count" value="20" class="w-full p-2 rounded input-field"></div><button type="submit" class="w-full btn-primary text-white font-bold py-2 px-4 rounded">Start Offsets</button></form></div>
        </div>

        <div class="mt-8">
            <h2 class="text-2xl font-semibold mb-4">Capture Status</h2>
            <div id="status-log" class="p-4 rounded-lg"><p>Initializing...</p></div>
            <div id="status-current" class="mt-2 text-lg"></div>
            <button id="stop-btn" class="w-full mt-4 btn-danger text-white font-bold py-2 px-4 rounded hidden">Stop Current Capture</button>
        </div>
    </div>

    <script>
        const log = document.getElementById('status-log');
        const statusCurrent = document.getElementById('status-current');
        const stopBtn = document.getElementById('stop-btn');
        const bulbContainer = document.getElementById('bulb-input-container');
        const bulbInput = document.getElementById('bulb-duration');

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
                if (configName === 'shutterspeed') {
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

        // --- Event Listeners ---
        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('.camera-config-select').forEach(fetchCameraConfig);
        });

        document.body.addEventListener('change', (event) => {
            if (event.target.matches('.camera-config-select')) {
                const configName = event.target.dataset.config;
                const value = event.target.value;
                setCameraConfig(configName, value);
                if (configName === 'shutterspeed') {
                    handleShutterChange();
                }
            }
        });

        document.getElementById('lights-form').addEventListener('submit', (e) => { e.preventDefault(); submitCapture('lights', { exposure: getExposureValue(), count: document.getElementById('lights-count').value }); });
        document.getElementById('darks-form').addEventListener('submit', (e) => { e.preventDefault(); submitCapture('darks', { exposure: getExposureValue(), count: document.getElementById('darks-count').value }); });
        document.getElementById('offsets-form').addEventListener('submit', (e) => { e.preventDefault(); submitCapture('offsets', { count: document.getElementById('offsets-count').value }); });
        stopBtn.addEventListener('click', async () => { addToLog('Sending stop request...'); try { const r = await fetch('/stop_capture', { method: 'POST' }); addToLog((await r.json()).message); } catch (err) { addToLog(`Error stopping: ${err}`); } stopBtn.classList.add('hidden'); });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/config/<config_name>', methods=['GET', 'POST'])
def api_config(config_name):
    """Generic endpoint to get or set a camera configuration value."""
    if config_name not in CONFIG_MAP:
        return jsonify({'error': f'Unknown config name: {config_name}'}), 404

    config_path = CONFIG_MAP[config_name]

    if request.method == 'GET':
        cmd = ["gphoto2", f"--get-config={config_path}"]
        stdout, stderr = run_gphoto_command(cmd)

        if stderr and "error" in stderr.lower():
            return jsonify({'error': stderr.strip()}), 500

        try:
            current_match = re.search(r"Current:\s*(.*)", stdout)
            current = current_match.group(1).strip() if current_match else None

            choices_matches = re.findall(r"Choice:\s*\d+\s*(.*)", stdout)
            choices = [{"value": m.strip()} for m in choices_matches]

            if not choices:
                return jsonify({'error': f'Could not parse choices for {config_name}.'}), 500

            return jsonify({'current': current, 'choices': choices})
        except Exception as e:
            return jsonify({'error': f"Failed to parse gphoto2 output: {e}"}), 500

    if request.method == 'POST':
        data = request.json
        value_to_set = data.get('value')
        if value_to_set is None:
            return jsonify({'status': 'error', 'message': 'No value provided'}), 400

        cmd = ["gphoto2", f"--set-config-value={config_path}={value_to_set}"]
        _, stderr = run_gphoto_command(cmd)

        if stderr and "error" in stderr.lower():
            return jsonify({'status': 'error', 'message': stderr.strip()}), 500

        return jsonify({'status': 'success', 'message': f'{config_name} set to {value_to_set}'})


@app.route('/start_capture', methods=['POST'])
def start_capture():
    """Starts a gphoto2 capture process."""
    global capture_process
    if capture_process and capture_process.poll() is None:
        return jsonify({'status': 'error', 'message': 'A capture is already in progress.'}), 400

    data = request.json
    capture_type = data.get('type')

    capture_dir = os.path.join(os.path.expanduser("~"), "astro_captures", capture_type)
    os.makedirs(capture_dir, exist_ok=True)

    env = os.environ.copy()
    env['LANG'] = 'C.UTF-8'

    cmd = ["gphoto2"]

    if capture_type in ['lights', 'darks']:
        exposure = data.get('exposure')
        count = data.get('count')
        if not exposure or not count:
            return jsonify({'status': 'error', 'message': 'Exposure and count are required.'}), 400

        filename_template = f"{capture_type}_%Y%m%d_%H%M%S_%C.arw"
        cmd.extend([
            "-I", str(exposure), "-F", str(count), "-B", str(exposure),
            "--capture-image-and-download", "--no-keep",
            "--filename", os.path.join(capture_dir, filename_template)
        ])

    elif capture_type == 'offsets':
        count = data.get('count')
        if not count:
            return jsonify({'status': 'error', 'message': 'Count is required.'}), 400

        filename_template = f"offsets_%Y%m%d_%H%M%S_%C.arw"
        cmd.extend([
            # For offsets, we assume the fastest shutter speed has been set via UI.
            # Interval of -1 means as fast as possible.
            "-F", str(count), "-I", "-1",
            "--capture-image-and-download", "--no-keep",
            "--filename", os.path.join(capture_dir, filename_template)
        ])
    else:
        return jsonify({'status': 'error', 'message': 'Invalid capture type.'}), 400

    try:
        capture_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                           preexec_fn=os.setsid, env=env)
        return jsonify({'status': 'started', 'message': f'Started {capture_type} capture. Command: {" ".join(cmd)}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to start gphoto2: {e}'}), 500


@app.route('/status')
def status():
    """Checks the status of the ongoing capture process."""
    global capture_process
    if capture_process and capture_process.poll() is None:
        return jsonify({'status': 'capturing', 'message': 'Capture in progress...'})
    else:
        if capture_process:
            stdout, stderr = capture_process.communicate()
            if capture_process.returncode == 0:
                message = "Capture completed successfully."
            else:
                message = f"Capture failed. Error: {stderr.strip()}"
            capture_process = None
            return jsonify({'status': 'finished', 'message': message})
        return jsonify({'status': 'idle', 'message': 'No capture in progress.'})


@app.route('/stop_capture', methods=['POST'])
def stop_capture():
    """Stops the currently running gphoto2 process."""
    global capture_process
    if capture_process and capture_process.poll() is None:
        try:
            os.killpg(os.getpgid(capture_process.pid), signal.SIGTERM)
            capture_process = None
            return jsonify({'status': 'stopped', 'message': 'Capture process terminated.'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Failed to stop process: {e}'}), 500
    return jsonify({'status': 'idle', 'message': 'No capture process was running.'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
