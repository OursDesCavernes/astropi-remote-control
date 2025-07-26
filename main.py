from flask import Flask, render_template_string, request, jsonify
import subprocess
import os
import signal

app = Flask(__name__)

# --- Global variable to hold the process ---
capture_process = None

# --- HTML & JavaScript Frontend ---
# Using Tailwind CSS for a clean, responsive layout.
# JavaScript will handle form submissions and update the UI without page reloads.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AstroPi Control</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .card {
            background-color: #1f2937; /* bg-gray-800 */
            color: #f3f4f6; /* text-gray-200 */
        }
        .btn-primary {
            background-color: #3b82f6; /* bg-blue-500 */
            transition: background-color 0.3s;
        }
        .btn-primary:hover {
            background-color: #2563eb; /* bg-blue-600 */
        }
        .btn-danger {
            background-color: #ef4444; /* bg-red-500 */
            transition: background-color: 0.3s;
        }
        .btn-danger:hover {
            background-color: #dc2626; /* bg-red-600 */
        }
        .input-field {
            background-color: #374151; /* bg-gray-700 */
            border-color: #4b5563; /* border-gray-600 */
        }
        #status-log {
            background-color: #111827; /* bg-gray-900 */
            font-family: 'monospace';
            height: 200px;
            overflow-y: scroll;
            border: 1px solid #4b5563; /* border-gray-600 */
        }
    </style>
</head>
<body class="bg-gray-900 text-white p-4 md:p-8">
    <div class="max-w-4xl mx-auto">
        <header class="text-center mb-8">
            <h1 class="text-4xl font-bold text-blue-400">AstroPi Camera Control</h1>
            <p class="text-gray-400">Control your astrophotography captures from your browser.</p>
        </header>

        <div id="controls" class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <!-- Lights Card -->
            <div class="card p-6 rounded-lg shadow-lg">
                <h2 class="text-2xl font-semibold mb-4 text-yellow-400">Lights</h2>
                <form id="lights-form" class="space-y-4">
                    <div>
                        <label for="lights-exposure" class="block mb-1 text-sm font-medium">Exposure (s)</label>
                        <input type="number" id="lights-exposure" value="30" class="w-full p-2 rounded input-field focus:ring-blue-500 focus:border-blue-500">
                    </div>
                    <div>
                        <label for="lights-count" class="block mb-1 text-sm font-medium">Number of Shots</label>
                        <input type="number" id="lights-count" value="10" class="w-full p-2 rounded input-field focus:ring-blue-500 focus:border-blue-500">
                    </div>
                    <button type="submit" class="w-full btn-primary text-white font-bold py-2 px-4 rounded">Start Lights</button>
                </form>
            </div>

            <!-- Darks Card -->
            <div class="card p-6 rounded-lg shadow-lg">
                <h2 class="text-2xl font-semibold mb-4 text-purple-400">Darks</h2>
                <form id="darks-form" class="space-y-4">
                    <div>
                        <label for="darks-exposure" class="block mb-1 text-sm font-medium">Exposure (s)</label>
                        <input type="number" id="darks-exposure" value="30" class="w-full p-2 rounded input-field focus:ring-blue-500 focus:border-blue-500">
                    </div>
                    <div>
                        <label for="darks-count" class="block mb-1 text-sm font-medium">Number of Shots</label>
                        <input type="number" id="darks-count" value="10" class="w-full p-2 rounded input-field focus:ring-blue-500 focus:border-blue-500">
                    </div>
                    <button type="submit" class="w-full btn-primary text-white font-bold py-2 px-4 rounded">Start Darks</button>
                </form>
            </div>

            <!-- Offsets Card -->
            <div class="card p-6 rounded-lg shadow-lg">
                <h2 class="text-2xl font-semibold mb-4 text-green-400">Offsets/Bias</h2>
                <form id="offsets-form" class="space-y-4">
                     <div>
                        <label for="offsets-count" class="block mb-1 text-sm font-medium">Number of Shots</label>
                        <input type="number" id="offsets-count" value="20" class="w-full p-2 rounded input-field focus:ring-blue-500 focus:border-blue-500">
                    </div>
                    <button type="submit" class="w-full btn-primary text-white font-bold py-2 px-4 rounded">Start Offsets</button>
                </form>
            </div>
        </div>

        <div class="mt-8">
            <h2 class="text-2xl font-semibold mb-4">Capture Status</h2>
            <div id="status-log" class="p-4 rounded-lg">
                <p>Ready. Select a capture type to begin.</p>
            </div>
            <div id="status-current" class="mt-2 text-lg"></div>
             <button id="stop-btn" class="w-full mt-4 btn-danger text-white font-bold py-2 px-4 rounded hidden">Stop Current Capture</button>
        </div>
    </div>

    <script>
        const log = document.getElementById('status-log');
        const statusCurrent = document.getElementById('status-current');
        const stopBtn = document.getElementById('stop-btn');

        function addToLog(message) {
            const p = document.createElement('p');
            p.textContent = `> ${message}`;
            log.appendChild(p);
            log.scrollTop = log.scrollHeight;
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
                } else {
                     addToLog(data.message);
                     checkStatus();
                }
            } catch (error) {
                addToLog(`Network or server error: ${error}`);
            }
        }

        async function checkStatus() {
            try {
                const response = await fetch('/status');
                const data = await response.json();

                if (data.status === 'capturing') {
                    statusCurrent.textContent = data.message;
                    setTimeout(checkStatus, 1000); // Poll every second
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

        document.getElementById('lights-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const exposure = document.getElementById('lights-exposure').value;
            const count = document.getElementById('lights-count').value;
            submitCapture('lights', { exposure, count });
        });

        document.getElementById('darks-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const exposure = document.getElementById('darks-exposure').value;
            const count = document.getElementById('darks-count').value;
            submitCapture('darks', { exposure, count });
        });

        document.getElementById('offsets-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const count = document.getElementById('offsets-count').value;
            submitCapture('offsets', { count });
        });

        stopBtn.addEventListener('click', async () => {
             addToLog('Sending stop request...');
             try {
                const response = await fetch('/stop_capture', { method: 'POST' });
                const data = await response.json();
                addToLog(data.message);
             } catch (error) {
                addToLog(`Error stopping capture: ${error}`);
             }
             stopBtn.classList.add('hidden');
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/start_capture', methods=['POST'])
def start_capture():
    """Starts a gphoto2 capture process."""
    global capture_process
    if capture_process and capture_process.poll() is None:
        return jsonify({'status': 'error', 'message': 'A capture is already in progress.'}), 400

    data = request.json
    capture_type = data.get('type')

    # --- Create a directory for the captures if it doesn't exist ---
    capture_dir = os.path.join(os.path.expanduser("~"), "astro_captures", capture_type)
    os.makedirs(capture_dir, exist_ok=True)

    # --- Construct gphoto2 command ---
    # NOTE: These commands assume gphoto2 is configured to download files.
    # The filename includes a timestamp to avoid overwrites.
    # The camera must be set to RAW format manually.

    cmd = ["gphoto2", "--set-config", "capturetarget=1"]  # Download to computer

    if capture_type == 'lights' or capture_type == 'darks':
        exposure = data.get('exposure')
        count = data.get('count')
        if not exposure or not count:
            return jsonify({'status': 'error', 'message': 'Exposure and count are required.'}), 400

        filename_template = f"{capture_type}_%Y%m%d_%H%M%S_%C"
        cmd.extend([
            "--set-config", f"shutterspeed={exposure}",
            "--frames", str(count),
            "--interval", "1",  # Small interval between shots
            "--filename", os.path.join(capture_dir, filename_template)
        ])

    elif capture_type == 'offsets':
        count = data.get('count')
        if not count:
            return jsonify({'status': 'error', 'message': 'Count is required.'}), 400

        filename_template = f"offsets_%Y%m%d_%H%M%S_%C"
        # For offsets, we want the fastest possible shutter speed.
        # '0' often corresponds to the fastest speed.
        cmd.extend([
            "--set-config", "shutterspeed=0",
            "--frames", str(count),
            "--interval", "-1",  # As fast as possible
            "--filename", os.path.join(capture_dir, filename_template)
        ])
    else:
        return jsonify({'status': 'error', 'message': 'Invalid capture type.'}), 400

    try:
        # Using preexec_fn to create a new process group, allowing us to kill the entire process tree.
        capture_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                           preexec_fn=os.setsid)
        return jsonify({'status': 'started', 'message': f'Started {capture_type} capture. PID: {capture_process.pid}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to start gphoto2: {e}'}), 500


@app.route('/status')
def status():
    """Checks the status of the ongoing capture process."""
    global capture_process
    if capture_process and capture_process.poll() is None:
        # Process is still running
        # We could try to read stdout here, but it can be blocking.
        # For a simple approach, we just confirm it's running.
        return jsonify({'status': 'capturing', 'message': 'Capture in progress...'})
    else:
        # Process is finished or was never started
        if capture_process:
            # Capture finished, get output
            stdout, stderr = capture_process.communicate()
            if capture_process.returncode == 0:
                message = "Capture completed successfully."
            else:
                message = f"Capture failed. Error: {stderr.strip()}"
            capture_process = None  # Clear the process
            return jsonify({'status': 'finished', 'message': message})
        return jsonify({'status': 'idle', 'message': 'No capture in progress.'})


@app.route('/stop_capture', methods=['POST'])
def stop_capture():
    """Stops the currently running gphoto2 process."""
    global capture_process
    if capture_process and capture_process.poll() is None:
        try:
            # Kill the entire process group to ensure gphoto2 and any children are terminated.
            os.killpg(os.getpgid(capture_process.pid), signal.SIGTERM)
            capture_process = None
            return jsonify({'status': 'stopped', 'message': 'Capture process terminated.'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Failed to stop process: {e}'}), 500
    return jsonify({'status': 'idle', 'message': 'No capture process was running.'})


if __name__ == '__main__':
    # Run on 0.0.0.0 to be accessible from any device on the network.
    app.run(host='0.0.0.0', port=5000, debug=True)
