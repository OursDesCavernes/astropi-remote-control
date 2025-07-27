import subprocess
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError
from typing import Optional, Tuple


# Custom Exception for when commander is busy
class BusyError(Exception):
    """Exception raised when a command is attempted while another is already running."""
    pass

class Commander:
    """
    A class to manage the execution of commands, ensuring single-instance
    execution, storing outputs, and providing blocking/non-blocking access to results.
    """

    def __init__(self):
        """
        Initializes the Commander.
        _is_busy: Flag indicating if a command is currently being processed.
        _last_stdout: Stores the standard output of the last completed command.
        _last_stderr: Stores the standard error of the last completed command.
        _current_future: Holds the Future object for the command currently submitted
                         to the executor.
        _executor: A ThreadPoolExecutor configured to run only one task at a time,
                   ensuring commands are executed sequentially.
        _lock: A threading.Lock to protect shared state variables from race conditions.
        """
        self._is_busy = False
        self._last_stdout = None
        self._last_stderr = None
        self._last_return_code = None
        self._current_future: Optional[Future] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()

    def _run_command_internal(self, cmd: list[str], timeout: int):
        """
        Internal helper method to execute a command.
        This method is designed to be run in a separate thread by the ThreadPoolExecutor.

        Args:
            cmd (list[str]): The command and its arguments as a list.
            timeout (int): The maximum time (in seconds) to wait for the command to complete.

        Returns:
            tuple[str, str]: A tuple containing (stdout, stderr) of the command.

        Raises:
            TimeoutError: If the command itself times out.
            FileNotFoundError: If the executable is not found.
            RuntimeError: For any other unexpected errors during subprocess execution.
        """
        env = os.environ.copy()
        env['LANG'] = 'C.UTF-8'  # Set LANG to ensure consistent output format

        try:
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,  # Decode stdout/stderr as text
                check=True, # Raise CalledProcessError if the command returns a non-zero exit code
                env=env,
                timeout=timeout
            )
            return process.stdout, process.stderr, process.returncode
        except subprocess.CalledProcessError as e:
            # Command exited with a non-zero status, return its output for debugging
            return e.stdout, e.stderr, e.returncode
        except subprocess.TimeoutExpired:
            # The command itself timed out
            raise TimeoutError("command timed out. Is the camera connected and responsive?")
        except FileNotFoundError:
            # executable not found in PATH
            raise FileNotFoundError("command not found. Is it installed and in your PATH?")
        except Exception as e:
            # Catch any other unexpected exceptions
            raise RuntimeError(f"An unexpected error occurred during execution: {e}")

    def _update_outputs_on_completion(self, future: Future):
        """
        Callback function executed when a command's Future completes (either successfully or with an error).
        This method updates the stored outputs and resets the busy state.
        It runs in the executor's thread.

        Args:
            future (Future): The Future object that just completed.
        """
        with self._lock:
            # Only update if this future is still the one we are tracking as current.
            # This prevents issues if execute_command is called very rapidly.
            if future is self._current_future:
                try:
                    # Retrieve the result. This will re-raise any exceptions that occurred
                    # during _run_gphoto_command_internal.
                    stdout, stderr, return_code = future.result()
                    self._last_stdout = stdout
                    self._last_stderr = stderr
                    self._last_return_code = return_code
                except TimeoutError as e:
                    self._last_stdout = None
                    self._last_stderr = str(e) # Store the timeout message
                    self._last_return_code = -1
                except FileNotFoundError as e:
                    self._last_stdout = None
                    self._last_stderr = str(e) # Store the file not found message
                    self._last_return_code = -1
                except Exception as e:
                    # Catch any other exceptions and store an error message
                    self._last_stdout = None
                    self._last_stderr = f"Error during command execution: {e}"
                    self._last_return_code = -1
                finally:
                    # Reset the busy flag and clear the current future regardless of success/failure
                    self._is_busy = False
                    self._current_future = None

    def execute_command(self, cmd: list[str], timeout: int = 10, startup_timeout: int = 0):
        """
        Starts a command asynchronously in a separate thread.

        Args:
            cmd (list[str]): The command and its arguments as a list.
            timeout (int): The maximum time (in seconds) to allow the command to run.
            startup_timeout (int): The maximum time (in seconds) to allow the command to wait before starting.

        Raises:
            BusyError: If a command is already running.
        """
        while True:
            with self._lock:
                if self._is_busy:
                    if startup_timeout <= 0:
                        raise BusyError("A command is already running. Please wait or retrieve its output.")
                    else:
                        time.sleep(1)
                        startup_timeout -= 1
                        continue


                self._is_busy = True
                # Submit the internal command runner to the executor.
                # The result will be accessible via the returned Future object.
                self._current_future = self._executor.submit(self._run_command_internal, cmd, timeout)
                # Attach a callback to update outputs and state when the command completes
                self._current_future.add_done_callback(self._update_outputs_on_completion)
                break

    def wait_for_outputs(self, timeout: int = None) -> Tuple[str, str, int]:
        """
        Blocks until the currently running command completes and returns its outputs.
        If no command is currently running, it immediately returns the outputs of the last
        completed command without blocking.

        Args:
            timeout (int, optional): The maximum time (in seconds) to wait for the command.
                                     If None, waits indefinitely.

        Returns:
            tuple[str, str]: A tuple containing (stdout, stderr) of the command.

        Raises:
            TimeoutError: If the wait_for_outputs call itself times out.
            Exception: Any exception raised by the command execution.
        """
        with self._lock:
            # If no command is currently active, return the last stored outputs immediately.
            # This covers cases where no command was ever run, or the last one completed
            # and its outputs were already processed.
            if not self._is_busy or self._current_future is None:
                return self._last_stdout, self._last_stderr, self._last_return_code

            # Capture the future to wait on. This prevents issues if a new command is
            # executed immediately after this method is called but before the wait.
            future_to_wait_on = self._current_future

        try:
            # Wait for the specific future to complete.
            # The _update_outputs_on_completion callback will handle updating
            # _last_stdout/_last_stderr and resetting _is_busy and _current_future.
            stdout, stderr, return_code = future_to_wait_on.result(timeout=timeout)
            return stdout, stderr, return_code
        except TimeoutError:
            # This specific TimeoutError is from the .result() call itself,
            # meaning the wait_for_outputs call timed out before the command finished.
            raise
        except Exception:
            # Re-raise any exceptions that occurred during the command's execution.
            # These would have been set as the future's exception by _run_gphoto_command_internal.
            raise

    def get_last_outputs(self) -> Tuple[str, str, int]:
        """
        Returns the outputs of the most recently completed command.
        This is a non-blocking method.

        If a command is currently running, this method returns the outputs from the
        command that completed *before* the current one started. The outputs of the
        current command will only be available after it completes.

        Returns:
            tuple[str, str]: A tuple containing (stdout, stderr) of the last completed command.
        """
        with self._lock:
            # The _update_outputs_on_completion callback ensures _last_stdout and _last_stderr
            # are always up-to-date with the last *completed* command.
            return self._last_stdout, self._last_stderr, self._last_return_code

    def is_command_running(self):
        """
        Checks if a command is currently active (submitted but not yet completed).

        Returns:
            bool: True if a command is running, False otherwise.
        """
        with self._lock:
            return self._is_busy

    def reset(self):
        with self._lock:
            if not self._is_busy:
                self._last_stdout = None
                self._last_stderr = None
                self._last_return_code = None
            else:
                raise BusyError("can't reset while busy")

    def abort(self):
        with self._lock:
            if self._is_busy:
                # os.killpg(os.getpgid(pid), signal.SIGTERM)
                raise NotImplemented
            else:
                self.reset()

    def __del__(self):
        """
        Ensures the ThreadPoolExecutor is properly shut down when the Gphoto2Commander
        object is garbage collected. This prevents lingering threads.
        """
        self._executor.shutdown(wait=True)
