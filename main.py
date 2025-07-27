import time

from flask import Flask, render_template_string, request, jsonify, send_from_directory
import subprocess
import os
import signal
import re

from camera_manager import CameraManager, CameraUnknownSettingError, CameraReadError, CameraWriteError
from commander import Commander, BusyError

app = Flask(
    __name__,
    static_url_path='',
    static_folder='static'
)

# --- Global variable to hold the process ---
commander = Commander()
camera = CameraManager(commander=commander)

@app.route('/', defaults={'path': 'index.html'})
@app.route('/<path:path>')
def index(path):
    """Serves the static page."""
    return send_from_directory('static', path)


@app.route("/api/reload-camera", methods=['GET', 'POST'])
def reload_camera():
    """Reload camera settings"""
    camera.reload_camera()

@app.route('/api/config/<config_name>', methods=['GET', 'POST'])
def api_config(config_name):
    """Generic endpoint to get or set a camera configuration value."""
    try:
        if request.method == 'GET':
            current, choices = camera.read_setting(config_name)
            return jsonify({'current': current, 'choices': choices})

        if request.method == 'POST':
            data = request.json
            value_to_set = data.get('value')
            camera.apply_setting(setting=config_name, value=value_to_set)
            if value_to_set is None:
                return jsonify({'status': 'error', 'message': 'No value provided'}), 400
            return jsonify({'status': 'success', 'message': f'{config_name} set to {value_to_set}'})

    except CameraUnknownSettingError:
        return jsonify({'error': f'Unknown config name: {config_name}'}), 404
    except CameraReadError as e:
        return jsonify({'error': f'Could not parse choices for {config_name}: {e}'}), 500
    except CameraWriteError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    except BusyError:
        return jsonify({'error': f'timeout trying to run gphoto2 for {config_name}.'}), 500
    except Exception as e:
        return jsonify({'error': f"unknown error: {e}"}), 500

@app.route('/start_capture', methods=['POST'])
def start_capture():
    """Starts a gphoto2 capture process."""

    data = request.json
    capture_type = data.get('type')

    capture_dir = os.path.join(os.path.expanduser("~"), "astro_captures", capture_type)
    os.makedirs(capture_dir, exist_ok=True)

    cmd = ["gphoto2"]
    timeout = 10


    count = int(data.get('count'))

    filename_template = f"{capture_type}_%Y%m%d_%H%M%S.%C"
    exposure = int(camera.read_setting("shutterspeed")[0])
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
        return jsonify({'status': 'error', 'message': 'A task is already in progress.'}), 400
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
