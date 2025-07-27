# Example Usage:
import time

from gphoto2commander import Commander, Gphoto2BusyError

if __name__ == "__main__":
    commander = Commander()

    # 1. Execute a command and get outputs blocking
    print("--- Executing `gphoto2 --version` (blocking) ---")
    try:
        commander.execute_command(["gphoto2", "--version"])
        stdout, stderr, _ = commander.wait_for_outputs(timeout=20) # Wait up to 20 seconds
        print("STDOUT:\n", stdout)
        if stderr:
            print("STDERR:\n", stderr)
    except Gphoto2BusyError as e:
        print(f"Error: {e}")
    except (TimeoutError, FileNotFoundError, RuntimeError) as e:
        print(f"Command Error: {e}")

    print("\n--- Checking last outputs (non-blocking) after first command ---")
    stdout, stderr, _ = commander.get_last_outputs()
    print("Last STDOUT:\n", stdout)
    if stderr:
        print("Last STDERR:\n", stderr)
    print(f"Is command running? {commander.is_command_running()}")


    # 2. Execute a command and try to execute another immediately (expecting busy error)
    print("\n--- Executing `gphoto2 --auto-detect` (async) ---")
    try:
        commander.execute_command(["gphoto2", "--auto-detect"], timeout=30)
        print("Command submitted successfully. It's running in the background.")
        print(f"Is command running? {commander.is_command_running()}")

        print("\n--- Trying to execute another command immediately (expecting busy error) ---")
        try:
            commander.execute_command(["gphoto2", "--list-ports"])
        except Gphoto2BusyError as e:
            print(f"Caught expected error: {e}")

        # Get last outputs (should be from --version command, as --auto-detect is still running)
        print("\n--- Checking last outputs (non-blocking) while command is running ---")
        stdout, stderr, _ = commander.get_last_outputs()
        print("Last STDOUT (from previous command):\n", stdout)
        if stderr:
            print("Last STDERR (from previous command):\n", stderr)
        print(f"Is command running? {commander.is_command_running()}")

        # Wait for the --auto-detect command to finish
        print("\n--- Waiting for `gphoto2 --auto-detect` to complete ---")
        stdout, stderr, _ = commander.wait_for_outputs(timeout=60) # Wait longer for auto-detect
        print("STDOUT (from --auto-detect):\n", stdout)
        if stderr:
            print("STDERR (from --auto-detect):\n", stderr)

    except (TimeoutError, FileNotFoundError, RuntimeError) as e:
        print(f"Command Error: {e}")

    print(f"\nIs command running after completion? {commander.is_command_running()}")

    # 3. Get last outputs after all commands are done
    print("\n--- Checking last outputs (non-blocking) after all commands completed ---")
    stdout, stderr, _ = commander.get_last_outputs()
    print("Last STDOUT:\n", stdout)
    if stderr:
        print("Last STDERR:\n", stderr)

    # 4. Example of a command that might time out (if gphoto2 is slow or camera not connected)
    print("\n--- Executing a command with a short timeout (may fail) ---")
    try:
        commander.execute_command(["gphoto2", "--list-config"], timeout=2) # Very short timeout
        print("Command submitted, waiting for results...")
        stdout, stderr, _ = commander.wait_for_outputs(timeout=5)
        print("STDOUT:\n", stdout)
        if stderr:
            print("STDERR:\n", stderr)
    except Gphoto2BusyError as e:
        print(f"Error: {e}")
    except TimeoutError as e:
        print(f"Caught expected TimeoutError: {e}")
    except (FileNotFoundError, RuntimeError) as e:
        print(f"Command Error: {e}")

    print("\n--- Final check of last outputs ---")
    stdout, stderr, _ = commander.get_last_outputs()
    print("Last STDOUT:\n", stdout)
    if stderr:
        print("Last STDERR:\n", stderr)