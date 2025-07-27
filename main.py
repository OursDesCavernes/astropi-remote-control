import time

from flask import Flask, render_template_string, request, jsonify, send_from_directory
import subprocess
import os
import signal
import re

from commander import Commander, BusyError

app = Flask(
    __name__,
    static_url_path='',
    static_folder='static'
)

# --- Global variable to hold the process ---
commander = Commander()

# --- Configuration Mapping ---
# Maps simple names to the full gphoto2 config paths.
CONFIG_MAP = {
    'shutterspeed': '/main/capturesettings/shutterspeed',
    'iso': '/main/imgsettings/iso',
    'f-number': '/main/capturesettings/f-number'
}


@app.route('/', defaults={'path': 'index.html'})
@app.route('/<path:path>')
def index(path):
    """Serves the static page."""
    return send_from_directory('static', path)


@app.route('/api/config/<config_name>', methods=['GET', 'POST'])
def api_config(config_name):
    """Generic endpoint to get or set a camera configuration value."""
    if config_name not in CONFIG_MAP:
        return jsonify({'error': f'Unknown config name: {config_name}'}), 404

    config_path = CONFIG_MAP[config_name]

    if request.method == 'GET':
        try:
            commander.execute_command(
                ["gphoto2", f"--get-config={config_path}"],
                startup_timeout=10,
                timeout=20
            )
        except BusyError:
            return jsonify({'error': f'timeout trying to run gphoto2 for {config_name}.'}), 500
        stdout, stderr, _ = commander.wait_for_outputs(timeout=20)

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

        commander.execute_command(
            ["gphoto2", f"--set-config-value={config_path}={value_to_set}"],
            startup_timeout=10,
            timeout=20
        )
        stdout, stderr, _ = commander.wait_for_outputs(timeout=20)

        if stderr and "error" in stderr.lower():
            return jsonify({'status': 'error', 'message': stderr.strip()}), 500

        return jsonify({'status': 'success', 'message': f'{config_name} set to {value_to_set}'})


@app.route('/start_capture', methods=['POST'])
def start_capture():
    """Starts a gphoto2 capture process."""

    data = request.json
    capture_type = data.get('type')

    capture_dir = os.path.join(os.path.expanduser("~"), "astro_captures", capture_type)
    os.makedirs(capture_dir, exist_ok=True)

    env = os.environ.copy()
    env['LANG'] = 'C.UTF-8'

    cmd = ["gphoto2"]
    timeout = 10


    exposure = int(data.get('exposure'))
    count = int(data.get('count'))
    if not exposure or not count:
        return jsonify({'status': 'error', 'message': 'Exposure and count are required.'}), 400

    filename_template = f"{capture_type}_%Y%m%d_%H%M%S.%C"

    if capture_type in ['lights', 'darks']:
        cmd.extend(["-B", str(exposure)])
        timeout = (exposure + 2) * count + 10
    elif capture_type == 'offsets':
        exposure = 1
        timeout = 5*count + 10  # Assume 5secs per download + 10 sec startup
    else:
        return jsonify({'status': 'error', 'message': 'Invalid capture type.'}), 400
    cmd.extend([
        "-I", str(exposure+1), "-F", str(count),
        "--capture-image-and-download", "--no-keep",
        "--filename", os.path.join(capture_dir, filename_template)
    ])

    try:
        commander.execute_command(cmd,timeout=timeout, startup_timeout=10)
        return jsonify({'status': 'started', 'message': f'Started {capture_type} capture. Command: {" ".join(cmd)}'})
    except BusyError:
        return jsonify({'status': 'error', 'message': 'A capture is already in progress.'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to start gphoto2: {e}'}), 500


@app.route('/status')
def status():
    """Checks the status of the ongoing capture process."""
    if commander.is_command_running():
        return jsonify({'status': 'capturing', 'message': 'Capture in progress...'})
    else:
        _, stderr, last_return_code = commander.get_last_outputs()
        if last_return_code is not None:
            if last_return_code == 0:
                message = "Capture completed successfully."
            else:
                message = f"Capture failed. Error: {stderr.strip()}"
            # commander.reset()
            return jsonify({'status': 'finished', 'message': message})
        return jsonify({'status': 'idle', 'message': 'No capture in progress.'})


@app.route('/stop_capture', methods=['POST'])
def stop_capture():
    """Stops the currently running gphoto2 process."""
    if commander.is_command_running():
        try:
            commander.abort()
            return jsonify({'status': 'stopped', 'message': 'Capture process terminated.'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'Failed to stop process: {e}'}), 500
    return jsonify({'status': 'idle', 'message': 'No capture process was running.'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
